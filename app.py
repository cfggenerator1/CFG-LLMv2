import os
import io
import base64
import networkx as nx
import pydot
from flask import Flask, render_template, request, url_for, jsonify
from dotenv import load_dotenv
import traceback
from openai import OpenAI

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate_cfg_route():
    try:
        user_input = request.form['user_input']
        prompt = f"Create a control flow graph in DOT format for the following scenario: {user_input}. Include nodes and edges in valid DOT syntax, without additional explanations."

        # Call OpenAI API
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}]
        )
        
        dot_code = response.choices[0].message.content.strip()
        
        # Extract the relevant DOT code
        start_index = dot_code.index("digraph")
        end_index = dot_code.rindex("}") + 1
        dot_code = dot_code[start_index:end_index]
        
        # Calculate metrics
        metrics = calculate_cyclomatic_complexity(dot_code)

        # Generate the graph image
        graph = pydot.graph_from_dot_data(dot_code)[0]
        png_string = graph.create_png(prog='dot')
        
        # Encode the image
        encoded_image = base64.b64encode(png_string).decode('utf-8')
        
        return render_template('index.html', cfg_image=encoded_image, metrics=metrics)
    except Exception as e:
        app.logger.error(f"An error occurred: {str(e)}")
        app.logger.error(traceback.format_exc())
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
