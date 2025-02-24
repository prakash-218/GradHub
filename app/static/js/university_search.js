function setupUniversitySearch(input) {
    const resultsDiv = input.parentElement.querySelector('.search-results');
    let searchTimeout;

    input.addEventListener('input', function() {
        clearTimeout(searchTimeout);
        const query = this.value.trim();
        
        if (query.length < 2) {
            resultsDiv.style.display = 'none';
            return;
        }

        searchTimeout = setTimeout(async () => {
            try {
                const response = await fetch(`/api/universities/search?q=${encodeURIComponent(query)}`);
                const universities = await response.json();
                
                resultsDiv.innerHTML = '';
                universities.forEach(uni => {
                    const div = document.createElement('div');
                    div.className = 'search-result-item';
                    div.textContent = `${uni.name} (${uni.country})`;
                    div.onclick = () => {
                        input.value = uni.name;
                        resultsDiv.style.display = 'none';
                    };
                    resultsDiv.appendChild(div);
                });
                resultsDiv.style.display = universities.length ? 'block' : 'none';
            } catch (error) {
                console.error('Error searching universities:', error);
            }
        }, 300);
    });

    // Hide results when clicking outside
    document.addEventListener('click', function(e) {
        if (!input.contains(e.target)) {
            resultsDiv.style.display = 'none';
        }
    });
} 