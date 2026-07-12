
// static/js/documents.js

document.addEventListener('DOMContentLoaded', () => {
    const documentsListContainer = document.getElementById('documentsList'); // The <ul> or <div> for doc items
    const emptyDocumentsStateDiv = document.getElementById('emptyDocumentsState');
    const chatInputField = document.getElementById('chatInput'); // To add [Document: ...] to
    const documentUploadButton = document.getElementById('documentUploadBtn'); // The upload button in the doc panel
    const documentFileInputHidden = document.getElementById('documentFileInput'); // Hidden file input

    // --- Helper to create SVG icon string based on file type ---
    function getFileIconSvg(fileExtension) {
        let iconPath = '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline>'; // Default
        switch (fileExtension.toLowerCase()) {
            case 'pdf':
                iconPath = '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline>';
                break;
            case 'docx':
            case 'doc':
                iconPath = '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline>';
                break;
            case 'xlsx':
            case 'xls':
            case 'csv':
                iconPath = '<rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><line x1="3" y1="9" x2="21" y2="9"></line><line x1="9" y1="21" x2="9" y2="9"></line>';
                break;
            case 'pptx':
            case 'ppt':
                iconPath = '<path d="M2 3h20v18H2z"></path><path d="M12 3v18"></path>';
                break;
            // Add more cases as needed
        }
        return `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${iconPath}</svg>`;
    }

    // --- Function to render the document list ---
    function renderDocumentList(documentNames) {
        if (!documentsListContainer) {
            console.error("Document list container not found!");
            return;
        }

        // Clear any existing static/placeholder items, BUT NOT the empty state div
        // We select only '.document-item' children to remove.
        const itemsToRemove = documentsListContainer.querySelectorAll('.document-item');
        itemsToRemove.forEach(item => item.remove());

        if (documentNames && documentNames.length > 0) {
            if (emptyDocumentsStateDiv) emptyDocumentsStateDiv.style.display = 'none';

            documentNames.forEach((docName, index) => {
                const fileNameParts = docName.split('.');
                const fileExt = fileNameParts.length > 1 ? fileNameParts.pop().toLowerCase() : 'file';
                
                const documentItem = document.createElement('div');
                documentItem.className = 'document-item';
                // Use a more robust data-id if you have unique IDs from backend, otherwise filename is okay for display
                documentItem.setAttribute('data-id', `doc-${index}-${docName.replace(/[^a-zA-Z0-9-_]/g, '')}`);
                documentItem.setAttribute('data-doctype', fileExt);
                documentItem.setAttribute('tabindex', '0'); // For accessibility

                documentItem.innerHTML = `
                    <div class="document-icon">
                        ${getFileIconSvg(fileExt)}
                    </div>
                    <div class="document-info">
                        <div class="document-name" title="${docName}">${docName}</div>
                        <div class="document-meta">
                            <span>${fileExt.toUpperCase()}</span>
                            <!-- Meta dot and size can be added if available -->
                            <!-- <span class="document-meta-dot"></span> -->
                            <!-- <span>File Size</span> -->
                        </div>
                    </div>
                `;
                
                // Attach event listener for click
                documentItem.addEventListener('click', () => handleDocumentItemClick(documentItem, docName));
                // Attach event listener for keyboard interaction
                documentItem.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        handleDocumentItemClick(documentItem, docName);
                    }
                });

                documentsListContainer.appendChild(documentItem);
            });
        } else {
            if (emptyDocumentsStateDiv) emptyDocumentsStateDiv.style.display = 'flex'; // Show empty state
        }
    }

    // --- Function to handle click on a document item ---
    function handleDocumentItemClick(itemElement, docName) {
        if (!documentsListContainer || !chatInputField) return;

        // Toggle 'active' class
        const allItems = documentsListContainer.querySelectorAll('.document-item');
        allItems.forEach(item => {
            if (item !== itemElement) item.classList.remove('active');
        });
        itemElement.classList.toggle('active');

        // Add reference to chat input
        const documentReference = `[Doc: ${docName}] `;
        if (itemElement.classList.contains('active')) { // Only add if activating
            if (!chatInputField.value.includes(documentReference)) {
                chatInputField.value = documentReference + chatInputField.value;
            }
        } else { // If deactivating, remove the reference (optional, can be complex)
            // chatInputField.value = chatInputField.value.replace(documentReference, '').trim();
        }
        chatInputField.focus();
        // Trigger input event for textarea auto-resize if you have that in chat.js
        chatInputField.dispatchEvent(new Event('input', { bubbles: true }));
    }

    // --- Load processed document names from localStorage ---
    function loadAndDisplayProcessedDocuments() {
        const storedDocsJson = localStorage.getItem('activeDocs');
        let processedDocumentNames = [];
        if (storedDocsJson) {
            try {
                processedDocumentNames = JSON.parse(storedDocsJson);
                if (!Array.isArray(processedDocumentNames)) {
                    processedDocumentNames = []; // Ensure it's an array
                }
            } catch (e) {
                console.error("Error parsing 'activeDocs' from localStorage:", e);
                processedDocumentNames = [];
            }
        }
        
        console.log("Processed documents loaded from localStorage:", processedDocumentNames);
        renderDocumentList(processedDocumentNames);
    }

    // --- Handle the upload button within the document panel ---
    // This would ideally trigger the same upload flow as the hero page,
    // which is complex to replicate fully without refactoring into shared modules.
    // For now, it can just trigger the hidden file input. The backend processing
    // would need to be handled, and then this list refreshed.
    if (documentUploadButton && documentFileInputHidden) {
        documentUploadButton.addEventListener('click', () => {
            documentFileInputHidden.click();
        });

        documentFileInputHidden.addEventListener('change', (event) => {
            if (event.target.files && event.target.files.length > 0) {
                // This is a simplified version. In a full app, you'd send these
                // files to the backend for staging & processing, then refresh the list.
                alert(`File(s) selected: ${Array.from(event.target.files).map(f=>f.name).join(', ')}. 
Full upload from chat panel not yet implemented. Please use the main upload page.`);
                // To fully implement:
                // 1. Send these files to '/stage_file'
                // 2. Then, somehow trigger '/process_staged_files' or add to a queue
                // 3. Then call loadAndDisplayProcessedDocuments() or update list from backend response.
                event.target.value = null; // Reset file input
            }
        });
    }


    // --- Initial load ---
    loadAndDisplayProcessedDocuments();

    // Optional: Listen for storage changes if another tab modifies 'activeDocs'
    // window.addEventListener('storage', (event) => {
    //     if (event.key === 'activeDocs') {
    //         loadAndDisplayProcessedDocuments();
    //     }
    // });
});
