import os
import io
import base64
import networkx as nx
import pydot
from flask import Flask, render_template, request, url_for, jsonify, session
from dotenv import load_dotenv
import traceback
from openai import OpenAI

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__, static_url_path='/static', static_folder='static')
app.secret_key = os.getenv("FLASK_SECRET_KEY", "default_secret_key")  # Set a secret key for sessions

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
    if 'history' not in session:
        session['history'] = []
    return render_template('index.html', history=session['history'])

@app.route('/generate', methods=['POST'])
def generate_cfg_route():
    try:
        user_input = request.form['user_input']
        feedback = request.form.get('feedback', '')
        
        prompt = f"""
        Create a control flow graph in DOT format for the following scenario: {user_input}
        
        Requirements:
        1. Use valid DOT syntax without additional explanations.
        2. Include clear and descriptive node labels.
        3. Ensure all paths and decision points are represented.
        4. Use appropriate shapes for different node types (e.g., diamonds for decision nodes).
        
        Previous attempts: {len(session['history'])}
        
        User feedback: {feedback}
        
        Based on this information, generate an improved and accurate control flow graph.
        """

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}]
        )
        
        dot_code = response.choices[0].message.content.strip()
        
        start_index = dot_code.index("digraph")
        end_index = dot_code.rindex("}") + 1
        dot_code = dot_code[start_index:end_index]
        
        metrics = calculate_cyclomatic_complexity(dot_code)

        graph = pydot.graph_from_dot_data(dot_code)[0]
        png_string = graph.create_png(prog='dot')
        
        encoded_image = base64.b64encode(png_string).decode('utf-8')
        
        session['history'].append({
            'input': user_input,
            'feedback': feedback,
            'image': encoded_image,
            'metrics': metrics
        })
        session.modified = True
        
        return render_template('index.html', cfg_image=encoded_image, metrics=metrics, history=session['history'])
    except Exception as e:
        app.logger.error(f"An error occurred: {str(e)}")
        app.logger.error(traceback.format_exc())
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500

@app.route('/clear_history', methods=['POST'])
def clear_history():
    session['history'] = []
    return jsonify({"message": "History cleared successfully"})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
