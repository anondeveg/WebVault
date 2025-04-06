document.addEventListener('DOMContentLoaded', function() {
    const addButton = document.getElementById('addButton');
    const noteInput = document.getElementById('noteInput');
    const statusDiv = document.getElementById('status');

    addButton.addEventListener('click', async function() {
        try {
            // Get the current tab
            const tabs = await browser.tabs.query({active: true, currentWindow: true});
            const currentTab = tabs[0];
            
            // Prepare the data
            const data = {
                url: currentTab.url,
                note: noteInput.value.trim()
            };

            // Send the request to your Flask server
            const response = await fetch('http://localhost:5000/add', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-API-Key': 'your-secret-api-key-123'
                },
                body: JSON.stringify(data)
            });

            const result = await response.json();

            if (response.ok) {
                showStatus('Bookmark added successfully!', 'success');
                noteInput.value = ''; // Clear the note input
                // Close the popup after a short delay
                setTimeout(() => {
                    window.close();
                }, 1000);
            } else {
                showStatus(result.error || 'Error adding bookmark', 'error');
            }
        } catch (error) {
            console.error('Error:', error);
            showStatus('Error: Could not connect to Numan Vault. Make sure the server is running.', 'error');
        }
    });

    function showStatus(message, type) {
        statusDiv.textContent = message;
        statusDiv.className = `status ${type}`;
        statusDiv.style.display = 'block';
        
        // Hide the status message after 3 seconds
        setTimeout(() => {
            statusDiv.style.display = 'none';
        }, 3000);
    }
}); 