from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from google.cloud import geminidataanalytics
from google.api_core import exceptions as google_exceptions
from typing import List, Optional
import uuid
import os

security = HTTPBearer()
from datetime import datetime
from pydantic import BaseModel
from google.protobuf.json_format import MessageToDict
from dotenv import load_dotenv
from .auth import SCOPES

load_dotenv(override=True)

PROJECT_ID = os.getenv("PROJECT_ID")

# Pydantic models for request/response
class BigQueryTableReference(BaseModel):
    project_id: str
    dataset_id: str
    table_id: str

class LookerExploreReference(BaseModel):
    looker_instance_uri: str
    lookml_model: str
    explore: str

class DatasourceReferences(BaseModel):
    bq: Optional[BigQueryTableReference] = None
    looker: Optional[LookerExploreReference] = None

class Context(BaseModel):
    datasource_references: DatasourceReferences
    system_instruction: str

class DataAgentRequest(BaseModel):
    display_name: str
    description: str
    system_instruction: str
    data_source: str  # "BigQuery" or "Looker"
    bq_project_id: Optional[str] = None
    bq_dataset_id: Optional[str] = None
    bq_table_id: Optional[str] = None
    looker_instance_url: Optional[str] = None
    looker_model: Optional[str] = None
    looker_explore: Optional[str] = None

class DataAgentUpdateRequest(BaseModel):
    display_name: str
    description: str
    system_instruction: str

class DataAgentResponse(BaseModel):
    name: str
    display_name: Optional[str]
    description: Optional[str]
    create_time: Optional[datetime]
    update_time: Optional[datetime]
    system_instruction: Optional[str]
    datasource_references: Optional[dict]

router = APIRouter()

from .auth_utils import validate_token
from google.oauth2.credentials import Credentials

async def get_credentials(auth: HTTPAuthorizationCredentials = Depends(security)):
    """Create Google credentials from Bearer token"""
    try:
        token = auth.credentials
        
        # Create credentials object directly from the token
        creds = Credentials(
            token=token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.getenv("GOOGLE_CLIENT_ID"),
            client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
            scopes=SCOPES
        )
        return creds
    except Exception as e:
        print(f"Error creating credentials: {str(e)}")  # Add logging
        raise HTTPException(status_code=401, detail=f"Failed to create credentials: {str(e)}")

@router.get("/")
async def list_agents(creds = Depends(get_credentials)):
    """List all data agents"""
    try:
        import logging
        logging.basicConfig(level=logging.DEBUG)
        logger = logging.getLogger("list_agents")

        logger.debug("Initializing DataAgentServiceClient with provided credentials.")
        client = geminidataanalytics.DataAgentServiceClient(credentials=creds)

        logger.debug("Creating ListDataAgentsRequest for project: %s", PROJECT_ID)
        request = geminidataanalytics.ListDataAgentsRequest(
            parent=f"projects/{PROJECT_ID}/locations/global"
        )

        logger.debug("Sending request to list data agents.")
        agents = list(client.list_data_agents(request=request))
        logger.debug("Received %d agents from the API.", len(agents))

        response = []
        for agent in agents:
            try:
                # Convert protobuf to dict and then manually build the response
                agent_dict = MessageToDict(agent._pb)
                logger.debug("Processing agent: %s", agent_dict.get("name", "Unknown"))

                # Ensure create_time and update_time are properly formatted
                if 'createTime' in agent_dict and agent_dict['createTime']:
                    agent_dict['create_time'] = agent.create_time.isoformat()
                else:
                    agent_dict['create_time'] = None

                if 'updateTime' in agent_dict and agent_dict['updateTime']:
                    agent_dict['update_time'] = agent.update_time.isoformat()
                else:
                    agent_dict['update_time'] = None

                # Extract nested fields safely
                published_context = agent_dict.get('dataAnalyticsAgent', {}).get('publishedContext', {})
                agent_dict['system_instruction'] = published_context.get('systemInstruction')
                agent_dict['datasource_references'] = published_context.get('datasourceReferences')

                response.append(agent_dict)
            except Exception as agent_error:
                logger.error("Error processing agent: %s", str(agent_error), exc_info=True)

        logger.debug("Successfully processed all agents.")
        return {"agents": response}

    except google_exceptions.GoogleAPICallError as e:
        logger.error("Google API call error: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"API error fetching agents: {str(e)}")
    except Exception as e:
        logger.error("Unexpected error: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

@router.post("/")
async def create_agent(agent_data: DataAgentRequest, creds = Depends(get_credentials)):
    """Create a new data agent"""
    try:
        client = geminidataanalytics.DataAgentServiceClient(credentials=creds)

        # Create agent object
        agent = geminidataanalytics.DataAgent()
        agent_id = f"a{uuid.uuid4()}"
        agent.name = f"projects/{PROJECT_ID}/locations/global/dataAgents/{agent_id}"
        agent.display_name = agent_data.display_name
        agent.description = agent_data.description

        # Set up datasource references
        datasource_references = geminidataanalytics.DatasourceReferences()

        if agent_data.data_source == "BigQuery":
            if not all([agent_data.bq_project_id, agent_data.bq_dataset_id, agent_data.bq_table_id]):
                raise HTTPException(status_code=400, detail="BigQuery project_id, dataset_id, and table_id are required")

            bigquery_table_reference = geminidataanalytics.BigQueryTableReference()
            bigquery_table_reference.project_id = agent_data.bq_project_id
            bigquery_table_reference.dataset_id = agent_data.bq_dataset_id
            bigquery_table_reference.table_id = agent_data.bq_table_id
            datasource_references.bq.table_references = [bigquery_table_reference]

        elif agent_data.data_source == "Looker":
            if not all([agent_data.looker_instance_url, agent_data.looker_model, agent_data.looker_explore]):
                raise HTTPException(status_code=400, detail="Looker instance URL, model, and explore are required")

            looker_explore_reference = geminidataanalytics.LookerExploreReference()
            looker_explore_reference.looker_instance_uri = agent_data.looker_instance_url
            looker_explore_reference.lookml_model = agent_data.looker_model
            looker_explore_reference.explore = agent_data.looker_explore
            datasource_references.looker.explore_references = [looker_explore_reference]

        else:
            raise HTTPException(status_code=400, detail="Invalid data source. Must be 'BigQuery' or 'Looker'")

        # Set up published context
        published_context = geminidataanalytics.Context()
        published_context.datasource_references = datasource_references
        published_context.system_instruction = agent_data.system_instruction

        agent.data_analytics_agent.published_context = published_context

        # Create the agent
        request = geminidataanalytics.CreateDataAgentRequest(
            parent=f"projects/{PROJECT_ID}/locations/global",
            data_agent_id=agent_id,
            data_agent=agent
        )

        operation = client.create_data_agent(request=request)
        created_agent = operation.result()  # Resolve the operation to get the actual DataAgent object

        return {
            "message": f"Agent '{agent_data.display_name}' successfully created",
            "agent": {
                "name": created_agent.name,
                "display_name": created_agent.display_name,
                "description": created_agent.description
            }
        }

    except google_exceptions.GoogleAPICallError as e:
        raise HTTPException(status_code=500, detail=f"API error creating agent: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

@router.put("/{agent_name}")
async def update_agent(agent_name: str, agent_data: DataAgentUpdateRequest, creds = Depends(get_credentials)):
    """Update an existing data agent"""
    try:
        client = geminidataanalytics.DataAgentServiceClient(credentials=creds)

        # Get existing agent first
        get_request = geminidataanalytics.GetDataAgentRequest(name=agent_name)
        existing_agent = client.get_data_agent(request=get_request)

        # Update agent
        agent = geminidataanalytics.DataAgent()
        agent.name = agent_name
        agent.display_name = agent_data.display_name
        agent.description = agent_data.description

        # Keep existing datasource references
        published_context = geminidataanalytics.Context()
        published_context.datasource_references = existing_agent.data_analytics_agent.published_context.datasource_references
        published_context.system_instruction = agent_data.system_instruction
        agent.data_analytics_agent.published_context = published_context

        request = geminidataanalytics.UpdateDataAgentRequest(
            data_agent=agent,
            update_mask="*"
        )

        updated_agent = client.update_data_agent(request=request)

        return {
            "message": "Agent successfully updated",
            "agent": {
                "name": updated_agent.name,
                "display_name": updated_agent.display_name,
                "description": updated_agent.description
            }
        }

    except google_exceptions.GoogleAPICallError as e:
        raise HTTPException(status_code=500, detail=f"API error updating agent: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

@router.delete("/projects/{project_id}/locations/{location}/dataAgents/{agent_id}")
async def delete_agent(project_id: str, location: str, agent_id: str, creds = Depends(get_credentials)):
    agent_name = f"projects/{project_id}/locations/{location}/dataAgents/{agent_id}"
    print(f"Deleting agent with name: {agent_name}")  # Debugging log
    try:
        client = geminidataanalytics.DataAgentServiceClient(credentials=creds)

        request = geminidataanalytics.DeleteDataAgentRequest(name=agent_name)
        print(f"DeleteDataAgentRequest created: {request}")  # Debugging log

        response = client.delete_data_agent(request=request)
        print(f"DeleteDataAgentResponse: {response}")  # Debugging log

        return {"message": "Agent successfully deleted"}

    except google_exceptions.GoogleAPICallError as e:
        print(f"Google API Call Error: {str(e)}")  # Debugging log
        raise HTTPException(status_code=500, detail=f"API error deleting agent: {str(e)}")
    except Exception as e:
        print(f"Unexpected Error: {str(e)}")  # Debugging log
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
