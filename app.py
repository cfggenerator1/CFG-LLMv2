import os
import io
import base64
import logging
from datetime import datetime
import networkx as nx
import pydot
from flask import Flask, render_template, request, jsonify, session, send_from_directory
from dotenv import load_dotenv
import traceback
import openai
from logging.handlers import RotatingFileHandler

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__, 
    static_folder='static',
    template_folder='templates'
)

# Configure app
app.secret_key = os.getenv("SECRET_KEY", "fallback_secret_key")
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['SESSION_PERMANENT'] = False

# Initialize OpenAI client
openai.api_key = os.getenv("OPENAI_API_KEY")

# Set up logging
if not os.path.exists('logs'):
    os.makedirs('logs')

logging.basicConfig(level=logging.INFO)
file_handler = RotatingFileHandler(
    'logs/app.log', 
    maxBytes=1024 * 1024,  # 1MB
    backupCount=10
)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)
app.logger.info('CFG Generator startup')

def setup_folders():
    """Ensure required folders exist"""
    folders = ['static', 'static/css', 'templates', 'logs']
    for folder in folders:
        if not os.path.exists(folder):
            os.makedirs(folder)
            app.logger.info(f'Created folder: {folder}')

def calculate_cyclomatic_complexity(dot_code):
    """Calculate cyclomatic complexity and other metrics from DOT code"""
    try:
        graph = nx.DiGraph(nx.nx_pydot.read_dot(io.StringIO(dot_code)))
        num_nodes = graph.number_of_nodes()
        num_edges = graph.number_of_edges()
        cyclomatic_complexity = num_edges - num_nodes + 2
        
        # Calculate additional metrics

        return {
            'Number of Nodes': num_nodes,
            'Number of Edges': num_edges,
            'Cyclomatic Complexity': cyclomatic_complexity,
        }
    except Exception as e:
        app.logger.error(f"Error calculating metrics: {str(e)}")
        return {
            'Number of Nodes': 0,
            'Number of Edges': 0,
            'Cyclomatic Complexity': 0,
        }

def generate_graph_image(dot_code):
    """Generate PNG image from DOT code and return base64 encoded string"""
    try:
        graph = pydot.graph_from_dot_data(dot_code)[0]
        png_string = graph.create_png(prog='dot')
        return base64.b64encode(png_string).decode('utf-8')
    except Exception as e:
        app.logger.error(f"Error generating graph image: {str(e)}")
        raise

def validate_dot_code(dot_code):
    """Validate DOT code structure and syntax"""
    try:
        pydot.graph_from_dot_data(dot_code)
        return True
    except Exception as e:
        app.logger.warning(f"Invalid DOT code: {str(e)}")
        return False

@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory('static', path)

@app.route('/')
def index():
    """Render the main page"""
    if 'chat_history' not in session:
        session['chat_history'] = []
        session['last_dot_code'] = ''
    return render_template('index.html', chat_history=session['chat_history'])

@app.route('/generate', methods=['POST'])
def generate_cfg_route():
    """Handle graph generation requests"""
    try:
        user_input = request.form.get('user_input')
        if not user_input:
            return jsonify({"error": "No input provided"}), 400

        chat_history = session.get('chat_history', [])
        last_dot_code = session.get('last_dot_code', '')
        
        # Prepare messages for OpenAI
        messages = [{"role": "system", "content": """You are a control flow graph generator. 
        Generate or modify graphs in DOT format based on user requests. 
        Ensure the generated DOT code is valid and includes proper node connections and attributes."""}]
        
        # Add chat history for context
        for chat in chat_history[-5:]:  # Only use last 5 messages for context
            messages.append({
                "role": "user" if chat['type'] == 'user' else "assistant",
                "content": chat['content']
            })
        
        # Create appropriate prompt based on context
        if last_dot_code and not user_input.lower().startswith(('create', 'generate', 'make')):
            prompt = f"""Modify the following control flow graph based on the user's request.
            Previous DOT code:
            {last_dot_code}

            User's modification request: {user_input}

            Provide the complete modified DOT code."""
        else:
            prompt = f"""Create a control flow graph in DOT format for the following scenario: {user_input}. 
            Include nodes and edges in valid DOT syntax. 
            Use appropriate node shapes and edge attributes to represent the flow clearly."""

        messages.append({"role": "user", "content": prompt})

        # Get response from OpenAI
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.7,
            max_tokens=1000
        )
        
        assistant_response = response.choices[0].message['content'].strip()
        
        # Extract DOT code
        try:
            start_index = assistant_response.index("digraph")
            end_index = assistant_response.rindex("}") + 1
            dot_code = assistant_response[start_index:end_index]
        except ValueError:
            return jsonify({"error": "Failed to generate valid graph"}), 400
        
        # Validate DOT code
        if not validate_dot_code(dot_code):
            return jsonify({"error": "Generated invalid graph structure"}), 400
        
        # Generate image and calculate metrics
        metrics = calculate_cyclomatic_complexity(dot_code)
        encoded_image = generate_graph_image(dot_code)
        
        # Update session data
        chat_history.append({"type": "user", "content": user_input})
        chat_history.append({"type": "assistant", "content": assistant_response})
        session['last_dot_code'] = dot_code
        session['chat_history'] = chat_history
        session.modified = True
        
        return jsonify({
            'chat_history': chat_history,
            'cfg_image': encoded_image,
            'metrics': metrics
        })
                             
    except Exception as e:
        app.logger.error(f"Error in generate_cfg_route: {str(e)}")
        app.logger.error(traceback.format_exc())
        return jsonify({
            "error": "An error occurred while generating the graph",
            "details": str(e)
        }), 500

@app.route('/repair', methods=['POST'])
def repair_cfg():
    """Handle graph repair requests"""
    try:
        feedback = request.form.get('feedback')
        if not feedback:
            return jsonify({"error": "No feedback provided"}), 400
            
        last_dot_code = session.get('last_dot_code', '')
        if not last_dot_code:
            return jsonify({"error": "No previous graph found to repair"}), 400

        chat_history = session.get('chat_history', [])
        
        # Create repair-specific prompt
        repair_prompt = f"""Please repair the following control flow graph based on the user's feedback.
        
        Current DOT code:
        {last_dot_code}
        
        User's feedback:
        {feedback}
        
        Please analyze the feedback and provide a corrected version of the DOT code that addresses the issues.
        Maintain the graph's consistency and ensure all connections make logical sense.
        The response should contain valid DOT code."""

        messages = [
            {"role": "system", "content": "You are a control flow graph repair specialist. Analyze feedback and improve DOT format graphs while maintaining their logical consistency."},
            {"role": "user", "content": repair_prompt}
        ]

        # Get response from OpenAI
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.7,
            max_tokens=1000
        )
        
        assistant_response = response.choices[0].message['content'].strip()
        
        # Extract DOT code
        try:
            start_index = assistant_response.index("digraph")
            end_index = assistant_response.rindex("}") + 1
            repaired_dot_code = assistant_response[start_index:end_index]
        except ValueError:
            return jsonify({"error": "Failed to generate valid repair"}), 400
        
        # Validate repaired DOT code
        if not validate_dot_code(repaired_dot_code):
            return jsonify({"error": "Generated invalid graph structure during repair"}), 400
        
        # Calculate new metrics and generate new image
        metrics = calculate_cyclomatic_complexity(repaired_dot_code)
        encoded_image = generate_graph_image(repaired_dot_code)
        
        # Update session data
        chat_history.append({"type": "user", "content": f"Feedback: {feedback}"})
        chat_history.append({"type": "assistant", "content": f"Repaired graph based on feedback:\n{assistant_response}"})
        session['last_dot_code'] = repaired_dot_code
        session['chat_history'] = chat_history
        session.modified = True
        
        return jsonify({
            'chat_history': chat_history,
            'cfg_image': encoded_image,
            'metrics': metrics,
            'message': 'Graph successfully repaired based on feedback'
        })

    except Exception as e:
        app.logger.error(f"Error in repair_cfg: {str(e)}")
        app.logger.error(traceback.format_exc())
        return jsonify({
            "error": "An error occurred while repairing the graph",
            "details": str(e)
        }), 500

@app.route('/clear', methods=['POST'])
def clear_history():
    """Clear session data"""
    try:
        session.clear()
        return jsonify({"status": "success"})
    except Exception as e:
        app.logger.error(f"Error clearing history: {str(e)}")
        return jsonify({"error": "Failed to clear history"}), 500

@app.errorhandler(404)
def not_found_error(error):
    return jsonify({"error": "Resource not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    app.logger.error(f"Server Error: {error}")
    return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    setup_folders()
    port = int(os.environ.get("PORT", 5001))
    app.run(host='0.0.0.0', port=port, debug=True)
