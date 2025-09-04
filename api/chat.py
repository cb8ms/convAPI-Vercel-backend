from fastapi import APIRouter, HTTPException, Request, Depends
from google.cloud import geminidataanalytics
from google.api_core import exceptions as google_exceptions
from typing import List, Optional, Dict, Any
import os
import json
from datetime import datetime
from pydantic import BaseModel
from google.protobuf.json_format import MessageToDict
import pandas as pd
from dotenv import load_dotenv
import asyncio

from .auth import validate_token

load_dotenv(override=True)

PROJECT_ID = os.getenv("PROJECT_ID")
LOOKER_CLIENT_ID = os.getenv("LOOKER_CLIENT_ID")
LOOKER_CLIENT_SECRET = os.getenv("LOOKER_CLIENT_SECRET")
LOOKER_CLIENT_ID = os.getenv("LOOKER_CLIENT_ID")
LOOKER_CLIENT_SECRET = os.getenv("LOOKER_CLIENT_SECRET")

# Pydantic models
class ConversationResponse(BaseModel):
    name: str
    create_time: Optional[datetime]
    last_used_time: Optional[datetime]
    agents: List[str]

class MessageRequest(BaseModel):
    text: str

class MessageResponse(BaseModel):
    type: str  # "user" or "assistant"
    content: Dict[str, Any]
    timestamp: Optional[datetime]

class ChatResponse(BaseModel):
    messages: List[MessageResponse]

router = APIRouter()

def is_looker_agent(agent) -> bool:
    """Check if agent uses Looker datasource"""
    datasource_references = agent.data_analytics_agent.published_context.datasource_references
    return "looker" in datasource_references

def format_message_response(message) -> Dict[str, Any]:
    """Format message for API response"""
    if hasattr(message, 'user_message') and message.user_message:
        return {
            "type": "user",
            "content": {"text": message.user_message.text},
            "timestamp": message.create_time.isoformat() if hasattr(message, 'create_time') and message.create_time else None
        }
    elif hasattr(message, 'system_message'):
        return format_system_message(message.system_message, message.create_time if hasattr(message, 'create_time') else None)
    elif hasattr(message, 'message'):  # Handle message wrapper
        return format_message_response(message.message)
    else:
        return {
            "type": "unknown",
            "content": {"raw": str(message)},
            "timestamp": None
        }

def format_system_message(system_message, timestamp) -> Dict[str, Any]:
    """Format system message based on its type"""
    content = {}

    if hasattr(system_message, 'text') and system_message.text:
        parts = getattr(system_message.text, 'parts', [])
        content = {
            "type": "text",
            "text": ''.join(parts)
        }
    elif hasattr(system_message, 'schema') and system_message.schema:
        content = format_schema_response(system_message.schema)
        content["type"] = "schema"
    elif hasattr(system_message, 'data') and system_message.data:
        content = format_data_response(system_message.data)
        content["type"] = "data"
    elif hasattr(system_message, 'chart') and system_message.chart:
        content = format_chart_response(system_message.chart)
        content["type"] = "chart"
    else:
        content = {
            "type": "unknown",
            "raw": str(system_message)
        }

    return {
        "type": "assistant",
        "message_type": content.get("type", "unknown"),
        "content": content,
        "timestamp": timestamp.isoformat() if timestamp else None
    }

def format_schema_response(schema_resp) -> Dict[str, Any]:
    """Format schema response for API"""
    result = {"type": "schema"}

    if hasattr(schema_resp, 'query') and schema_resp.query:
        result["query"] = {
            "question": schema_resp.query.question
        }
    elif hasattr(schema_resp, 'result') and schema_resp.result:
        result["status"] = "Schema resolved"
        datasources = []
        for datasource in schema_resp.result.datasources:
            ds_info = format_datasource(datasource)
            datasources.append(ds_info)
        result["datasources"] = datasources

    return result

def format_data_response(data_resp) -> Dict[str, Any]:
    """Format data response for API"""
    result = {}

    if hasattr(data_resp, 'query') and data_resp.query:
        result["query"] = {
            "name": data_resp.query.name,
            "question": data_resp.query.question,
            "datasources": []
        }
        for datasource in data_resp.query.datasources:
            ds_info = format_datasource(datasource)
            result["query"]["datasources"].append(ds_info)

    if hasattr(data_resp, 'generated_sql') and data_resp.generated_sql:
        result["generated_sql"] = data_resp.generated_sql

    if hasattr(data_resp, 'result') and data_resp.result:
        result["data_retrieved"] = True
        
        # Convert to DataFrame-like structure as in the original code
        fields = [field.name for field in data_resp.result.schema.fields]
        data = {}
        for row in data_resp.result.data:
            for field in fields:
                if field not in data:
                    data[field] = []
                data[field].append(row.get(field))
        
        result["data"] = {
            "fields": fields,
            "columns": data  # Using columns format instead of rows for better data handling
        }

    return result

def format_chart_response(chart_resp) -> Dict[str, Any]:
    """Format chart response for API"""
    print("DEBUG: Starting chart response formatting")
    print(f"DEBUG: Raw chart response: {chart_resp}")
    
    result = {"type": "chart"}

    if hasattr(chart_resp, 'query') and chart_resp.query:
        print(f"DEBUG: Chart query instructions: {chart_resp.query.instructions}")
        result["instructions"] = chart_resp.query.instructions

    if hasattr(chart_resp, 'result') and chart_resp.result:
        print("DEBUG: Chart has result")
        try:
            # Import chart processing utility
            from .chart_utils import process_chart
            
            # Get Vega-Lite spec using the same logic as Streamlit version
            chart_spec = process_chart(chart_resp.result.vega_config)
            if chart_spec:
                result["vega_config"] = chart_spec
            else:
                result["error"] = "Failed to process chart specification"
        
        except Exception as e:
            print(f"DEBUG: Error converting chart config: {str(e)}")
            import traceback
            traceback.print_exc()
            result["error"] = f"Error converting chart config: {str(e)}"

    return result

def format_datasource(datasource) -> Dict[str, Any]:
    """Format datasource information"""
    ds_info = {}

    if hasattr(datasource, 'studio_datasource_id'):
        ds_info["source_name"] = datasource.studio_datasource_id
    elif hasattr(datasource, 'looker_explore_reference'):
        ref = datasource.looker_explore_reference
        ds_info["source_name"] = f"lookmlModel: {ref.lookml_model}, explore: {ref.explore}, lookerInstanceUri: {ref.looker_instance_uri}"
    elif hasattr(datasource, 'bigquery_table_reference'):
        ref = datasource.bigquery_table_reference
        ds_info["source_name"] = f"{ref.project_id}.{ref.dataset_id}.{ref.table_id}"
    else:
        ds_info["source_name"] = "Unknown"

    # Format schema
    if hasattr(datasource, 'schema') and datasource.schema:
        fields = []
        for field in datasource.schema.fields:
            fields.append({
                "name": field.name,
                "type": field.type,
                "description": getattr(field, 'description', '-'),
                "mode": field.mode
            })
        ds_info["schema"] = {"fields": fields}

    return ds_info

@router.get("/conversations/{agent_name:path}")
async def list_conversations(agent_name: str, token_info = Depends(validate_token)):
    """List conversations for a specific agent"""
    try:
        print(f"DEBUG: Fetching conversations for agent: {agent_name}")
        
        # Create credentials from token_info
        from google.oauth2.credentials import Credentials
        creds = Credentials(
            token=token_info["token"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.getenv("GOOGLE_CLIENT_ID"),
            client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
            scopes=token_info["token_info"].get("scope", "").split()
        )
        
        client = geminidataanalytics.DataChatServiceClient(credentials=creds)

        request = geminidataanalytics.ListConversationsRequest(
            parent=f"projects/{PROJECT_ID}/locations/global",
            page_size=100,
        )

        convos = list(client.list_conversations(request=request))
        print(f"DEBUG: Found {len(convos)} total conversations")

        # Filter conversations for the specific agent
        # Try exact match first, then partial match
        agent_convos = []
        for c in convos:
            if c.agents:
                # Check if agent_name is in the agents list
                if agent_name in c.agents:
                    agent_convos.append(c)
                # Also check if the agent name matches partially (in case of different formats)
                elif any(agent_name.split('/')[-1] in agent for agent in c.agents):
                    agent_convos.append(c)

        print(f"DEBUG: Filtered to {len(agent_convos)} conversations for agent {agent_name}")
        if convos:
            print(f"DEBUG: Sample conversation agents: {convos[0].agents}")

        response_convos = []
        for convo in agent_convos:
            response_convos.append({
                "name": convo.name,
                "create_time": convo.create_time.isoformat() if hasattr(convo, 'create_time') and convo.create_time else None,
                "last_used_time": convo.last_used_time.isoformat() if hasattr(convo, 'last_used_time') and convo.last_used_time else None,
                "agents": list(convo.agents) if hasattr(convo, 'agents') else []
            })

        print(f"DEBUG: Returning {len(response_convos)} conversations")
        return {"conversations": response_convos}

    except google_exceptions.GoogleAPICallError as e:
        print(f"DEBUG: Google API error: {str(e)}")
        # If it's a permission or not found error, return empty list instead of failing
        if "403" in str(e) or "404" in str(e) or "PERMISSION" in str(e).upper():
            print("DEBUG: Returning empty conversations list due to permission/not found error")
            return {"conversations": []}
        raise HTTPException(status_code=500, detail=f"API error fetching conversations: {str(e)}")
    except Exception as e:
        print(f"DEBUG: Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

@router.post("/conversations")
async def create_conversation(agent_name: str, token_info = Depends(validate_token)):
    """Create a new conversation for an agent"""
    try:
        print(f"DEBUG: Creating conversation for agent: {agent_name}")
        
        # Create credentials from token_info
        from google.oauth2.credentials import Credentials
        creds = Credentials(
            token=token_info["token"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.getenv("GOOGLE_CLIENT_ID"),
            client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
            scopes=token_info["token_info"].get("scope", "").split()
        )
        
        client = geminidataanalytics.DataChatServiceClient(credentials=creds)

        conversation = geminidataanalytics.Conversation()
        conversation.agents = [agent_name]

        request = geminidataanalytics.CreateConversationRequest(
            parent=f"projects/{PROJECT_ID}/locations/global",
            conversation=conversation,
        )

        convo = client.create_conversation(request=request)
        print(f"DEBUG: Created conversation: {convo.name}")

        # Manually create the conversation dictionary
        convo_dict = {
            "name": convo.name,
            "create_time": convo.create_time.isoformat() if hasattr(convo, 'create_time') and convo.create_time else None,
            "last_used_time": convo.last_used_time.isoformat() if hasattr(convo, 'last_used_time') and convo.last_used_time else None,
            "agents": list(convo.agents) if hasattr(convo, 'agents') else []
        }

        return {"conversation": convo_dict}

    except google_exceptions.GoogleAPICallError as e:
        print(f"DEBUG: Google API error creating conversation: {str(e)}")
        raise HTTPException(status_code=500, detail=f"API error creating conversation: {str(e)}")
    except Exception as e:
        print(f"DEBUG: Unexpected error creating conversation: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

@router.get("/conversations/{conversation_name:path}/messages")
async def get_messages(conversation_name: str, token_info = Depends(validate_token)):
    """Get all messages for a conversation. conversation_name is the full path."""
    try:
        print(f"DEBUG: Fetching messages for conversation: {conversation_name}")
        
        # Create credentials from token_info
        from google.oauth2.credentials import Credentials
        creds = Credentials(
            token=token_info["token"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.getenv("GOOGLE_CLIENT_ID"),
            client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
            scopes=token_info["token_info"].get("scope", "").split()
        )
        
        client = geminidataanalytics.DataChatServiceClient(credentials=creds)

        request = geminidataanalytics.ListMessagesRequest(parent=conversation_name)
        msgs = list(client.list_messages(request=request))
        print(f"DEBUG: Found {len(msgs)} messages")

        # Convert messages to our format
        messages = []
        for msg_wrapper in msgs:
            try:
                message = msg_wrapper.message
                formatted_msg = format_message_response(message)
                messages.append(formatted_msg)
            except Exception as msg_error:
                print(f"DEBUG: Error formatting message: {str(msg_error)}")
                continue

        # Sort by timestamp if available
        messages.sort(key=lambda x: x.get('timestamp') or '', reverse=False)
        print(f"DEBUG: Returning {len(messages)} formatted messages")

        return {"messages": messages}

    except google_exceptions.GoogleAPICallError as e:
        print(f"DEBUG: Google API error fetching messages: {str(e)}")
        raise HTTPException(status_code=500, detail=f"API error fetching messages: {str(e)}")
    except Exception as e:
        print(f"DEBUG: Unexpected error fetching messages: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

from fastapi.responses import StreamingResponse
import json

@router.post("/conversations/{conversation_name:path}/messages")
async def send_message(conversation_name: str, message_req: MessageRequest, agent_name: str = None, token_info = Depends(validate_token)):
    """Send a message to a conversation and get streaming response."""
    async def chat_stream():
        try:
            # Create credentials from token_info
            from google.oauth2.credentials import Credentials
            creds = Credentials(
                token=token_info["token"],
                token_uri="https://oauth2.googleapis.com/token",
                client_id=os.getenv("GOOGLE_CLIENT_ID"),
                client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
                scopes=token_info["token_info"].get("scope", "").split()
            )
            
            client = geminidataanalytics.DataChatServiceClient(credentials=creds)

            # First, get the agent to check if it's a Looker agent
            agent_client = geminidataanalytics.DataAgentServiceClient(credentials=creds)
            agent_request = geminidataanalytics.GetDataAgentRequest(name=agent_name)
            agent = agent_client.get_data_agent(request=agent_request)

            # Create user message
            user_msg = geminidataanalytics.Message(user_message={"text": message_req.text})

            # Set up conversation reference
            convo_ref = geminidataanalytics.ConversationReference()
            convo_ref.conversation = conversation_name
            convo_ref.data_agent_context.data_agent = agent_name

            # Add Looker credentials if needed
            if is_looker_agent(agent):
                credentials = geminidataanalytics.Credentials()
                credentials.oauth.secret.client_id = LOOKER_CLIENT_ID
                credentials.oauth.secret.client_secret = LOOKER_CLIENT_SECRET
                convo_ref.data_agent_context.credentials = credentials

            # Create chat request
            req = geminidataanalytics.ChatRequest(
                parent=f"projects/{PROJECT_ID}/locations/global",
                messages=[user_msg],
                conversation_reference=convo_ref,
            )

            # Stream responses
            for message in client.chat(request=req):
                formatted_msg = format_message_response(message)
                # Send each message as a JSON string followed by a newline and force flush
                yield json.dumps(formatted_msg) + "\n"
                await asyncio.sleep(0)  # Allow the event loop to flush the response

        except Exception as e:
            # Send error message in the stream
            error_msg = {"error": str(e)}
            yield json.dumps(error_msg) + "\n"

    return StreamingResponse(chat_stream(), media_type="text/event-stream")
