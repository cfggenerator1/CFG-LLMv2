// script.js
document.addEventListener('DOMContentLoaded', function() {
    const chatMessages = document.getElementById('chatMessages');
    const userInput = document.getElementById('userInput');
    const sendBtn = document.getElementById('sendBtn');
    const repairBtn = document.getElementById('repairBtn');
    const clearBtn = document.getElementById('clearBtn');
    const graphImage = document.getElementById('graphImage');
    const loadingOverlay = document.getElementById('loadingOverlay');

    let isRepairMode = false;

    const WELCOME_MESSAGE = `• Welcome to the Control Flow Graph Generator!

• Key Features:
  - Create detailed flow diagrams
  - Get instant graph metrics
  - Optimize process layouts
  - Analyze flow complexity

• How to Use:
  - Type your process description
  - Click Generate to create graph
  - Use Refine for improvements

• Try describing a simple process to start!`;

    // Initialize UI state
    function initializeUI() {
        userInput.focus();
        repairBtn.classList.remove('active');
        isRepairMode = false;
        updateMetrics({ metrics: null });
        
        // Check if chat messages is empty and add welcome message
        if (chatMessages.children.length === 0) {
            addMessage(WELCOME_MESSAGE, 'assistant');
        }
    }

    // Format message content with proper bullet points
    function formatMessage(content) {
        return content.split('\n').map(line => {
            line = line.trim();
            if (line.startsWith('•')) {
                return `<div class="bullet-point">${line}</div>`;
            } else if (line.startsWith('-')) {
                return `<div class="sub-bullet">${line}</div>`;
            } else {
                return `<div>${line}</div>`;
            }
        }).join('');
    }

    // Add message to chat
    function addMessage(content, type) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${type}`;
        
        if (type === 'assistant') {
            messageDiv.innerHTML = formatMessage(content);
        } else {
            messageDiv.textContent = content;
        }
        
        chatMessages.appendChild(messageDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    // Update metrics display
    function updateMetrics(data) {
        const nodesMetric = document.getElementById('nodesMetric');
        const edgesMetric = document.getElementById('edgesMetric');
        const cyclomaticMetric = document.getElementById('cyclomaticMetric');
        
        if (data.metrics) {
            nodesMetric.textContent = data.metrics.nodes;
            edgesMetric.textContent = data.metrics.edges;
            cyclomaticMetric.textContent = data.metrics.cyclomatic;
        } else {
            nodesMetric.textContent = '-';
            edgesMetric.textContent = '-';
            cyclomaticMetric.textContent = '-';
        }
    }

    // Show/hide loading overlay
    function toggleLoading(show) {
        loadingOverlay.classList.toggle('hidden', !show);
    }

    // Generate graph
    async function generateGraph() {
        const input = userInput.value.trim();
        if (!input) return;

        try {
            // Show loading state
            toggleLoading(true);
            sendBtn.disabled = true;
            sendBtn.innerHTML = '<span class="btn-icon">↻</span> Generating...';
            
            const formData = new FormData();
            formData.append('user_input', input);
            formData.append('is_repair', isRepairMode);

            const response = await fetch('/generate', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();

            if (data.error) {
                throw new Error(data.error);
            }

            // Add user message
            addMessage(input, 'user');

            // Add assistant response if available
            if (data.chat_history && data.chat_history.length > 0) {
                const lastMessage = data.chat_history[data.chat_history.length - 1];
                if (lastMessage.type === 'assistant') {
                    addMessage(lastMessage.content, 'assistant');
                }
            }

            // Update graph visualization
            if (data.cfg_image) {
                graphImage.innerHTML = `<img src="data:image/png;base64,${data.cfg_image}" alt="Control Flow Graph">`;
            }

            // Update metrics
            if (data.metrics) {
                updateMetrics(data);
            }

            // Clear input
            userInput.value = '';
            userInput.focus();

        } catch (error) {
            addMessage(`• Error: ${error.message}`, 'assistant');
        } finally {
            // Reset states
            toggleLoading(false);
            sendBtn.disabled = false;
            sendBtn.innerHTML = '<span class="btn-icon">➤</span> Generate';
        }
    }

    // Clear chat and graph
    async function clearChat() {
        try {
            const response = await fetch('/clear_session', { method: 'POST' });
            const data = await response.json();
            
            if (data.status === 'success') {
                chatMessages.innerHTML = '';
                graphImage.innerHTML = '';
                userInput.value = '';
                updateMetrics({ metrics: null });
                
                // Add welcome message
                addMessage(WELCOME_MESSAGE, 'assistant');
                
                initializeUI();
            }
        } catch (error) {
            console.error('Error clearing session:', error);
        }
    }

    // Event listeners
    sendBtn.addEventListener('click', generateGraph);
    
    userInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            generateGraph();
        }
    });

    repairBtn.addEventListener('click', () => {
        isRepairMode = !isRepairMode;
        repairBtn.classList.toggle('active');
        userInput.placeholder = isRepairMode ? 
            "Describe how you'd like to improve the current graph..." :
            "Describe the process or flow you want to visualize...";
    });

    clearBtn.addEventListener('click', clearChat);

    // Initialize the UI
    initializeUI();
});
