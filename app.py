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

# Print current environment for debugging
app.logger.info(f"Current PATH: {os.environ.get('PATH', 'Not set')}")
app.logger.info(f"Current working directory: {os.getcwd()}")

def verify_graphviz_installation():
    """Verify Graphviz installation and log system information"""
    try:
        # Log all directories in PATH
        path_dirs = os.environ.get('PATH', '').split(':')
        app.logger.info("Searching in PATH directories:")
        for directory in path_dirs:
            app.logger.info(f"- {directory}")
            if os.path.exists(directory):
                files = os.listdir(directory)
                app.logger.info(f"  Contents: {files}")

        # Try to find dot using which
        try:
            dot_path = subprocess.check_output(['which', 'dot'], text=True).strip()
            app.logger.info(f"dot found at: {dot_path}")
        except subprocess.SubprocessError:
            app.logger.info("which dot command failed")

        # Check if Graphviz is accessible
        result = subprocess.run(['dot', '-V'], capture_output=True, text=True)
        app.logger.info(f"Graphviz version: {result.stdout}")
        return True
    except Exception as e:
        app.logger.error(f"Graphviz verification failed: {str(e)}")
        return False

def find_dot_executable():
    """Find the dot executable using multiple methods"""
    app.logger.info("Starting dot executable search")
    
    # First, verify Graphviz installation
    verify_graphviz_installation()
    
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
        '/opt/render/project/src/.apt/usr/bin/dot',  # Render-specific path
        os.path.join(os.getcwd(), '.apt/usr/bin/dot'),  # Alternative Render path
        'dot'
    ]
    
    for path in common_paths:
        app.logger.info(f"Checking path: {path}")
        if os.path.isfile(path):
            app.logger.info(f"Found dot at: {path}")
            try:
                subprocess.run([path, '-V'], capture_output=True, check=True)
                app.logger.info(f"Verified working dot at: {path}")
                return path
            except Exception as e:
                app.logger.error(f"Path {path} exists but execution failed: {str(e)}")

    # Method 3: Search in current directory and its parents
    current_dir = os.getcwd()
    while current_dir != '/':
        dot_path = os.path.join(current_dir, '.apt/usr/bin/dot')
        if os.path.isfile(dot_path):
            app.logger.info(f"Found dot in parent directory: {dot_path}")
            return dot_path
        current_dir = os.path.dirname(current_dir)

    app.logger.error("Could not find dot executable")
    return 'dot'  # Return default as fallback

def generate_graph_image(dot_code):
    """Generate graph image with Render-specific handling"""
    try:
        app.logger.info("Starting graph generation")
        
        # Find dot executable
        dot_path = find_dot_executable()
        app.logger.info(f"Using dot path: {dot_path}")
        
        # Update environment PATH
        bin_dir = os.path.dirname(dot_path)
        os.environ["PATH"] = f"{bin_dir}:{os.environ.get('PATH', '')}"
        
        # Try direct subprocess approach first
        try:
            app.logger.info("Attempting direct subprocess approach")
            process = subprocess.Popen(
                [dot_path, '-Tpng'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            png_string, stderr = process.communicate(input=dot_code.encode())
            if png_string:
                app.logger.info("Successfully generated PNG using subprocess")
                return base64.b64encode(png_string).decode('utf-8')
            else:
                app.logger.error(f"Subprocess PNG generation failed: {stderr.decode()}")
        except Exception as e:
            app.logger.error(f"Subprocess approach failed: {str(e)}")
        
        # Fallback to pydot approach
        try:
            app.logger.info("Attempting pydot approach")
            pydot.dot_path = dot_path
            graph = pydot.graph_from_dot_data(dot_code)[0]
            
            # Set graph attributes
            graph.set_rankdir('TB')
            graph.set_splines('ortho')
            
            # Generate PNG
            png_string = graph.create_png()
            if png_string:
                app.logger.info("Successfully generated PNG using pydot")
                return base64.b64encode(png_string).decode('utf-8')
            else:
                app.logger.error("Pydot generated empty PNG")
                
        except Exception as e:
            app.logger.error(f"Pydot approach failed: {str(e)}")
        
        return None
            
    except Exception as e:
        app.logger.error(f"Graph image generation error: {str(e)}")
        app.logger.exception("Full traceback:")
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
        # Remove "Complete DOT Graph Code" and dot code blocks
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
        
        # Add context from recent chat history
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
            
        # Generate graph image
        encoded_image = generate_graph_image(dot_code)
        if not encoded_image:
            return jsonify({
                "error": "Error generating graph visualization",
                "chat_history": chat_history
            }), 200
            
        # Calculate metrics
        metrics = calculate_metrics(dot_code)
        if not metrics:
            metrics = {"nodes": 0, "edges": 0, "cyclomatic": 0}
            
        # Update chat history
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

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5002))
    app.run(host='0.0.0.0', port=port, debug=True)
