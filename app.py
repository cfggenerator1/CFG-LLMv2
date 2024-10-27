from flask import Flask, render_template, request, jsonify, session
import os
import base64
import logging
import networkx as nx
import pydot
from dotenv import load_dotenv
import openai
from logging.handlers import RotatingFileHandler
import subprocess
import shutil

load_dotenv()

app = Flask(__name__, 
    static_folder='static',
    template_folder='templates'
)

# Constants
WELCOME_MESSAGE = """• Welcome to the Control Flow Graph Generator!

• Key Features:
  - Create detailed flow diagrams
  - Get instant graph metrics
  - Optimize process layouts
  - Analyze flow complexity

• How to Use:
  - Type your process description
  - Click Generate to create graph
  - Use Refine for improvements

• Try describing a simple process to start!"""

# Flask configuration
app.secret_key = os.getenv("SECRET_KEY", "fallback_secret_key")
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['SESSION_PERMANENT'] = False

openai.api_key = os.getenv("OPENAI_API_KEY")

# Set up logging
if not os.path.exists('logs'):
    os.makedirs('logs')

logging.basicConfig(level=logging.INFO)
file_handler = RotatingFileHandler(
    'logs/app.log', 
    maxBytes=1024 * 1024,
    backupCount=10
)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s'
))
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)

def find_dot_executable():
    """Find the dot executable using multiple methods"""
    app.logger.info("Starting dot executable search")
    
    # Method 1: Use shutil.which
    dot_path = shutil.which('dot')
    if dot_path:
        app.logger.info(f"Found dot using shutil.which: {dot_path}")
        return dot_path

    # Method 2: Check common paths
    common_paths = [
        '/usr/bin/dot',
        '/usr/local/bin/dot',
        '/bin/dot',
        '/opt/render/project/src/.apt/usr/bin/dot',
        os.path.join(os.getcwd(), '.apt/usr/bin/dot'),
        'dot'
    ]
    
    for path in common_paths:
        if os.path.isfile(path):
            try:
                subprocess.run([path, '-V'], capture_output=True, check=True)
                app.logger.info(f"Found working dot at: {path}")
                return path
            except Exception as e:
                app.logger.error(f"Path {path} exists but execution failed: {str(e)}")
                continue

    app.logger.error("Could not find dot executable")
    return 'dot'

def extract_dot_code(response_text):
    """Extract and validate DOT code from response"""
    try:
        if "digraph" not in response_text:
            return None
            
        start_idx = response_text.index("digraph")
        content = response_text[start_idx:]
        
        brace_count = 0
        end_idx = -1
        
        for i, char in enumerate(content):
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    end_idx = i + 1
                    break
        
        if end_idx == -1:
            return None
            
        dot_code = content[:end_idx].strip()
        return validate_dot_code(dot_code)
        
    except Exception as e:
        app.logger.error(f"DOT code extraction error: {str(e)}")
        return None

def validate_dot_code(dot_code):
    """Validate and fix common DOT code issues"""
    if not dot_code:
        return None
        
    try:
        # Remove any invalid characters
        dot_code = ''.join(char for char in dot_code if char.isprintable())
        
        # Ensure proper digraph structure
        if 'digraph' not in dot_code:
            dot_code = f'digraph G {{\n{dot_code}\n}}'
        
        # Fix common syntax issues
        dot_code = dot_code.replace('|', '"')
        dot_code = dot_code.replace('""', '"')
        dot_code = dot_code.replace('};};', '};')
        
        # Validate with pydot
        test_graph = pydot.graph_from_dot_data(dot_code)
        if not test_graph:
            return None
            
        return dot_code
    except Exception as e:
        app.logger.error(f"DOT code validation error: {str(e)}")
        return None

def generate_graph_image(dot_code):
    """Generate graph image with improved error handling"""
    try:
        app.logger.info("Starting graph generation")
        
        # Find dot executable
        dot_path = find_dot_executable()
        app.logger.info(f"Using dot path: {dot_path}")
        
        # Try subprocess approach first
        try:
            app.logger.info("Attempting subprocess approach")
            process = subprocess.Popen(
                [dot_path, '-Tpng'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            png_string, stderr = process.communicate(input=dot_code.encode())
            if png_string:
                return base64.b64encode(png_string).decode('utf-8')
        except Exception as e:
            app.logger.error(f"Subprocess approach failed: {str(e)}")
        
        # Fallback to pydot approach
        try:
            pydot.dot_path = dot_path
            graph = pydot.graph_from_dot_data(dot_code)[0]
            png_string = graph.create_png()
            if png_string:
                return base64.b64encode(png_string).decode('utf-8')
        except Exception as e:
            app.logger.error(f"Pydot approach failed: {str(e)}")
        
        return None
            
    except Exception as e:
        app.logger.error(f"Graph image generation error: {str(e)}")
        return None

def calculate_metrics(dot_code):
    """Calculate graph metrics from DOT code"""
    try:
        graphs = pydot.graph_from_dot_data(dot_code)
        if not graphs:
            return None
            
        edges = graphs[0].get_edge_list()
        graph = nx.DiGraph()
        
        for edge in edges:
            src = edge.get_source()
            dst = edge.get_destination()
            graph.add_edge(src.strip('"'), dst.strip('"'))
            
        nodes = graph.number_of_nodes()
        edges = graph.number_of_edges()
        cyclomatic = edges - nodes + 2
        
        return {
            "nodes": nodes,
            "edges": edges,
            "cyclomatic": cyclomatic
        }
    except Exception as e:
        app.logger.error(f"Error calculating metrics: {str(e)}")
        return None

def format_response(explanation):
    """Format the assistant's response in a bulleted list"""
    lines = [line.strip() for line in explanation.split('\n') if line.strip()]
    
    response_parts = []
    for line in lines:
        if "Complete DOT Graph Code" in line or "```dot" in line or "```" in line:
            continue
        elif line.startswith('•'):
            response_parts.append(line)
        elif line.startswith('-'):
            response_parts.append(f"  {line}")
        else:
            response_parts.append(f"• {line}")
    
    return '\n'.join(response_parts)

@app.route('/')
def index():
    if 'chat_history' not in session:
        session['chat_history'] = [{
            "type": "assistant",
            "content": WELCOME_MESSAGE
        }]
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate_cfg_route():
    try:
        user_input = request.form.get('user_input', '').strip()
        is_repair = request.form.get('is_repair', 'false') == 'true'
        
        if not user_input:
            return jsonify({"error": "Please provide a process description"}), 400

        chat_history = session.get('chat_history', [])
        
        # Create system message and prompt
        system_message = """You are a control flow graph generator assistant. 
        Generate DOT graph code that follows these rules:
        1. Use proper 'digraph G {...}' structure
        2. Include clear node labels
        3. Use -> for directed edges
        4. Add appropriate edge labels for conditions
        5. Maintain consistent formatting"""

        messages = [{"role": "system", "content": system_message}]
        
        for chat in chat_history[-5:]:
            messages.append({
                "role": "user" if chat['type'] == 'user' else "assistant",
                "content": chat['content']
            })

        current_prompt = f"""{'Improve the existing graph for' if is_repair else 'Create a control flow graph for'}: {user_input}
        
        Include in your response:
        1. A clear explanation of the process flow
        2. The complete DOT graph code
        3. Ensure all nodes are connected
        4. Use descriptive edge labels"""

        messages.append({"role": "user", "content": current_prompt})

        # Generate response
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.1,
            max_tokens=1000
        )
        
        assistant_response = response.choices[0].message['content'].strip()
        dot_code = extract_dot_code(assistant_response)
        
        if not dot_code:
            return jsonify({
                "error": "Could not generate valid graph structure. Please try rephrasing your description.",
                "chat_history": chat_history
            }), 200
            
        encoded_image = generate_graph_image(dot_code)
        if not encoded_image:
            return jsonify({
                "error": "Error generating graph visualization",
                "chat_history": chat_history
            }), 200
            
        metrics = calculate_metrics(dot_code)
        if not metrics:
            metrics = {"nodes": 0, "edges": 0, "cyclomatic": 0}
            
        explanation = assistant_response[:assistant_response.index("digraph")].strip()
        formatted_response = format_response(explanation)
        
        chat_history.append({"type": "user", "content": user_input})
        chat_history.append({"type": "assistant", "content": formatted_response})
        session['chat_history'] = chat_history
        
        return jsonify({
            'chat_history': chat_history,
            'cfg_image': encoded_image,
            'metrics': metrics
        })
        
    except Exception as e:
        app.logger.error(f"Generate CFG route error: {str(e)}")
        return jsonify({
            "error": "An unexpected error occurred. Please try again.",
            "chat_history": session.get('chat_history', [])
        }), 500

@app.route('/clear_session', methods=['POST'])
def clear_session():
    session.clear()
    session['chat_history'] = [{
        "type": "assistant",
        "content": WELCOME_MESSAGE
    }]
    return jsonify({"status": "success"})

@app.route('/verify-graphviz', methods=['GET'])
def verify_graphviz():
    """Endpoint to verify Graphviz installation"""
    try:
        dot_path = find_dot_executable()
        result = {
            'dot_path': dot_path,
            'path_env': os.environ.get('PATH', 'Not set'),
            'cwd': os.getcwd(),
            'dot_exists': os.path.exists(dot_path) if dot_path != 'dot' else None
        }
        
        try:
            version = subprocess.check_output([dot_path, '-V'], stderr=subprocess.STDOUT, text=True)
            result['version'] = version
        except Exception as e:
            result['version_error'] = str(e)
            
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5002))
    app.run(host='0.0.0.0', port=port, debug=True)
