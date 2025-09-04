import altair as alt
import json
import proto
from google.protobuf.json_format import MessageToDict

def _convert(v):
    """Convert protobuf message to a plain Python dict"""
    if isinstance(v, proto.marshal.collections.maps.MapComposite):
        return {k: _convert(v) for k, v in v.items()}
    elif isinstance(v, proto.marshal.collections.RepeatedComposite):
        return [_convert(el) for el in v]
    elif isinstance(v, (int, float, str, bool)):
        return v
    else:
        return MessageToDict(v)

def process_chart(vega_config) -> dict:
    """
    Convert Vega config to JSON chart specification
    Returns a dictionary that can be used directly with vega-lite
    """
    try:
        # Convert protobuf config to dict using the same logic as Streamlit version
        chart = alt.Chart.from_dict(_convert(vega_config))
        
        # Convert to JSON spec
        chart_spec = json.loads(chart.to_json())
        return chart_spec
    except Exception as e:
        print(f"Error processing chart: {e}")
        return None
