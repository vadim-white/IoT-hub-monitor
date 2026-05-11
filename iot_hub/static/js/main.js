// Main JavaScript functionality
$(document).ready(function() {
    console.log('IoT Hub Monitor loaded');
    
    // Dropdown menu
    $('.dropdown-toggle').click(function(e) {
        e.preventDefault();
        $(this).siblings('.dropdown-menu').toggle();
    });
    
    // Alert dismiss
    $('.alert').each(function() {
        setTimeout(() => {
            $(this).fadeOut();
        }, 5000);
    });
    
    // Device select change
    $('#device-select').change(function() {
        if ($(this).val()) {
            $(this).closest('form').submit();
        }
    });
});

// API functions
const API = {
    get: function(url) {
        return fetch(url, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCookie('csrftoken')
            }
        }).then(r => r.json());
    },
    
    post: function(url, data) {
        return fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCookie('csrftoken')
            },
            body: JSON.stringify(data)
        }).then(r => r.json());
    },
    
    getCookie: function(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }
};
