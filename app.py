import io
import base64
import json
import networkx as nx
import pydot
from openai import OpenAI

# Initialize OpenAI client
client = OpenAI()  # Assumes OPENAI_API_KEY is set in Cloudflare environment variables

def calculate_cyclomatic_complexity(dot_code):
    graph = nx.DiGraph(nx.nx_pydot.read_dot(io.StringIO(dot_code)))
    num_nodes = graph.number_of_nodes()
    num_edges = graph.number_of_edges()
    cyclomatic_complexity = num_edges - num_nodes + 2
    return {
        'Number of Nodes': num_nodes,
        'Number of Edges': num_edges,
        'Cyclomatic Complexity': cyclomatic_complexity
    }

def generate_cfg(request):
    try:
        body = json.loads(request.body)
        user_input = body.get('user_input', '')
        feedback = body.get('feedback', '')
        
        prompt = f"""
        Create a control flow graph in DOT format for the following scenario: {user_input}
        
        Requirements:
        1. Use valid DOT syntax without additional explanations.
        2. Include clear and descriptive node labels.
        3. Ensure all paths and decision points are represented.
        4. Use appropriate shapes for different node types (e.g., diamonds for decision nodes).
        
        User feedback: {feedback}
        
        Based on this information, generate an improved and accurate control flow graph.
        """

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}]
        )
        
        dot_code = response.choices[0].message.content.strip()
        
        metrics = calculate_cyclomatic_complexity(dot_code)

        graph = pydot.graph_from_dot_data(dot_code)[0]
        png_string = graph.create_png(prog='dot')
        
        encoded_image = base64.b64encode(png_string).decode('utf-8')
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'cfg_image': encoded_image,
                'dot_code': dot_code,
                'metrics': metrics
            })
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
