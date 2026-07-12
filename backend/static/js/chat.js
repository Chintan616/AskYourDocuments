
// Chat interface animations and enhanced interactions
document.addEventListener('DOMContentLoaded', () => {
    // Element references
    const messageItemsContainer = document.getElementById('messageItemsContainer');
    const chatForm = document.getElementById('chatForm');
    const chatInput = document.getElementById('chatInput');
    const messageList = document.getElementById('messageList');    // Apply animations and interactions to message bubbles
    function enhanceMessages() {
        try {
            // Target only unenhanced bubbles for better performance
            const chatBubbles = document.querySelectorAll('.chat-bubble:not([data-enhanced="true"])');
            
            if (!chatBubbles || chatBubbles.length === 0) return false;
            
            let bubbleCount = 0;
            
            chatBubbles.forEach(bubble => {
                try {
                    const message = bubble.querySelector('.chat-bubble-message');
                    if (!message) return;
                    
                    // Skip loading messages - they're handled separately
                    if (message.classList.contains('loading')) return;
                    
                    // Add entrance animation for new messages
                    bubble.style.opacity = '0';
                    bubble.style.transform = 'translateY(10px)';
                    
                    requestAnimationFrame(() => {
                        bubble.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
                        bubble.style.opacity = '1';
                        bubble.style.transform = 'translateY(0)';
                    });
                    
                    // Add ripple effect on click
                    bubble.addEventListener('click', function(e) {
                        message.classList.add('ripple');
                        
                        setTimeout(() => {
                            message.classList.remove('ripple');
                        }, 700);
                    });
                    
                    // Add hover animations
                    bubble.addEventListener('mouseenter', () => {
                        bubble.style.transition = 'all 0.3s ease';
                        if (bubble.classList.contains('sent')) {
                            message.style.transform = 'translateX(-2px)';
                        } else {
                            message.style.transform = 'translateX(2px)';
                        }
                    });
                    
                    bubble.addEventListener('mouseleave', () => {
                        message.style.transform = '';
                    });
                    
                    // Mark as enhanced
                    bubble.setAttribute('data-enhanced', 'true');
                    bubbleCount++;
                } catch (err) {
                    console.error('Error enhancing specific chat bubble:', err);
                }
            });
            
            return bubbleCount > 0;
        } catch (err) {
            console.error('Error in enhanceMessages function:', err);
            return false;
        }
    }// Update the loading indicator to use the new typing indicator animation
    function enhanceLoadingIndicator() {
        try {
            const loadingIndicators = document.querySelectorAll('.loading-indicator');
            
            if (!loadingIndicators || loadingIndicators.length === 0) return false;
            
            let anyEnhanced = false;
            
            loadingIndicators.forEach(indicator => {
                try {
                    // Check if already enhanced
                    if (indicator.getAttribute('data-enhanced') === 'true') return;
                    
                    // Create typing indicator element
                    const typingIndicator = document.createElement('div');
                    typingIndicator.className = 'typing-indicator';
                    
                    // Add three animated dots
                    for (let i = 0; i < 3; i++) {
                        const dot = document.createElement('span');
                        typingIndicator.appendChild(dot);
                    }
                    
                    // Replace existing content with the new typing indicator
                    indicator.innerHTML = '';
                    indicator.appendChild(typingIndicator);
                    
                    // Mark as enhanced
                    indicator.setAttribute('data-enhanced', 'true');
                    anyEnhanced = true;
                    
                    // Add fade-in animation
                    indicator.style.opacity = '0';
                    requestAnimationFrame(() => {
                        indicator.style.transition = 'opacity 0.3s ease';
                        indicator.style.opacity = '1';
                    });
                } catch (err) {
                    console.error('Error enhancing loading indicator:', err);
                }
            });
            
            return anyEnhanced;
        } catch (err) {
            console.error('Error in enhanceLoadingIndicator function:', err);
            return false;
        }
    }    // Apply animations to newly added messages
    const observeMessages = () => {
        try {
            if (!messageItemsContainer) {
                console.error('Message container not found, cannot observe');
                return;
            }
            
            // Create an observer instance
            const observer = new MutationObserver((mutations) => {
                try {
                    let newMessageNodes = [];
                    let newLoadingIndicator = false;
                    
                    mutations.forEach((mutation) => {
                        if (mutation.type === 'childList' && mutation.addedNodes.length) {
                            mutation.addedNodes.forEach(node => {
                                // Check if the node is a chat bubble
                                if (node.nodeType === 1 && node.classList && node.classList.contains('chat-bubble')) {
                                    if (node.querySelector('.loading-indicator')) {
                                        newLoadingIndicator = true;
                                    } else {
                                        newMessageNodes.push(node);
                                    }
                                }
                            });
                        }
                    });
                    
                    // Process in the next animation frame to ensure DOM stability
                    if (newMessageNodes.length > 0 || newLoadingIndicator) {
                        requestAnimationFrame(() => {
                            // First enhance new messages (non-loading)
                            if (newMessageNodes.length > 0) {
                                enhanceMessages();
                            }
                            
                            // Then handle loading indicators separately
                            if (newLoadingIndicator) {
                                enhanceLoadingIndicator();
                            }
                        });
                    }
                } catch (err) {
                    console.error('Error in mutation observer callback:', err);
                }
            });
            
            // Start observing the target node for configured mutations
            observer.observe(messageItemsContainer, { 
                childList: true,
                subtree: true,  // Also observe child nodes for changes
                attributes: true, // Observe attribute changes
                attributeFilter: ['class', 'data-enhanced'] // Only specific attributes
            });
            
            console.log('Message observer initialized with enhanced detection');
        } catch (err) {
            console.error('Error setting up message observer:', err);
        }
    };
    
    // Auto-resize the input as user types
    const setupInputResizing = () => {
        const MAX_HEIGHT = 240;
        
        chatInput.addEventListener('input', () => {
            chatInput.style.height = 'auto';
            const newHeight = Math.min(chatInput.scrollHeight, MAX_HEIGHT);
            chatInput.style.height = `${newHeight}px`;
        });
    };
    
    // Send button animation
    const animateSendButton = () => {
        const sendButton = document.getElementById('sendButton');
        
        if (!sendButton) return;
        
        sendButton.addEventListener('mouseenter', () => {
            // Add a slight rotation animation
            sendButton.style.transition = 'transform 0.3s ease';
            sendButton.style.transform = 'rotate(10deg) scale(1.1)';
        });
        
        sendButton.addEventListener('mouseleave', () => {
            sendButton.style.transform = '';
        });
        
        sendButton.addEventListener('click', () => {
            // Add a press animation on click
            sendButton.style.transform = 'scale(0.9)';
            setTimeout(() => {
                sendButton.style.transform = '';
            }, 150);
        });
    };    // Initialize all enhancements
    function initializeEnhancements(retryCount = 0) {
        try {
            // Make sure document is fully loaded before enhancing
            if (!messageItemsContainer || !chatForm || !chatInput || !messageList) {
                if (retryCount < 10) { // Limit retry attempts
                    console.warn(`Chat elements not found, retrying initialization (attempt ${retryCount + 1}/10)...`);
                    setTimeout(() => initializeEnhancements(retryCount + 1), 100);
                } else {
                    console.error('Failed to find chat elements after multiple attempts');
                }
                return;
            }
            
            // First observe mutations so we don't miss any new elements
            observeMessages();
            
            // Schedule enhancements in proper sequence with animation frame
            requestAnimationFrame(() => {
                // Enhance existing messages first
                enhanceMessages();
                
                // Then loading indicators
                enhanceLoadingIndicator();
                
                // Then UI components
                setupInputResizing();
                animateSendButton();
                
                console.log('Chat enhancements initialized successfully');
            });
        } catch (err) {
            console.error('Error during chat enhancement initialization:', err);
            
            // Retry initialization on error, but limit attempts
            if (retryCount < 3) {
                console.warn(`Retrying initialization due to error (attempt ${retryCount + 1}/3)...`);
                setTimeout(() => initializeEnhancements(retryCount + 1), 200);
            }
        }
    }
    
    // Use DOMContentLoaded since we're already inside that event,
    // but with a small delay to ensure all other scripts have run
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => setTimeout(initializeEnhancements, 10));
    } else {
        // DOM already loaded, initialize with a slight delay
        setTimeout(initializeEnhancements, 10);
    }
});

