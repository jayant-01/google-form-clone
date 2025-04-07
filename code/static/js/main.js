// Shared functionality for Google Forms Clone

// Show confirmation dialog before deleting items
function confirmDelete(message) {
    return window.confirm(message || 'Are you sure you want to delete this item?');
}

// Format dates to local string
function formatDate(dateString) {
    return new Date(dateString).toLocaleDateString();
}

// Show error messages
function showError(message) {
    const errorDiv = document.createElement('div');
    errorDiv.className = 'alert alert-danger alert-dismissible fade show';
    errorDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    
    const container = document.querySelector('.container');
    container.insertBefore(errorDiv, container.firstChild);
    
    // Auto dismiss after 5 seconds
    setTimeout(() => {
        errorDiv.remove();
    }, 5000);
}

// Show success messages
function showSuccess(message) {
    const successDiv = document.createElement('div');
    successDiv.className = 'alert alert-success alert-dismissible fade show';
    successDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    
    const container = document.querySelector('.container');
    container.insertBefore(successDiv, container.firstChild);
    
    // Auto dismiss after 3 seconds
    setTimeout(() => {
        successDiv.remove();
    }, 3000);
}

// Copy text to clipboard
async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        showSuccess('Copied to clipboard!');
    } catch (err) {
        showError('Failed to copy text');
    }
}

// Validate form input
function validateFormInput(input, rules = {}) {
    const value = input.value.trim();
    const errors = [];
    
    if (rules.required && !value) {
        errors.push('This field is required');
    }
    
    if (rules.minLength && value.length < rules.minLength) {
        errors.push(`Must be at least ${rules.minLength} characters`);
    }
    
    if (rules.maxLength && value.length > rules.maxLength) {
        errors.push(`Must be no more than ${rules.maxLength} characters`);
    }
    
    return errors;
}

// Handle form validation
function setupFormValidation(formElement, rules = {}) {
    const inputs = formElement.querySelectorAll('input, textarea, select');
    
    inputs.forEach(input => {
        input.addEventListener('blur', () => {
            const errors = validateFormInput(input, rules[input.name]);
            const errorContainer = input.parentElement.querySelector('.invalid-feedback') 
                || document.createElement('div');
            
            errorContainer.className = 'invalid-feedback';
            
            if (errors.length > 0) {
                input.classList.add('is-invalid');
                errorContainer.textContent = errors[0];
                if (!input.parentElement.contains(errorContainer)) {
                    input.parentElement.appendChild(errorContainer);
                }
            } else {
                input.classList.remove('is-invalid');
                errorContainer.remove();
            }
        });
    });
    
    formElement.addEventListener('submit', (e) => {
        let hasErrors = false;
        
        inputs.forEach(input => {
            const errors = validateFormInput(input, rules[input.name]);
            if (errors.length > 0) {
                hasErrors = true;
                input.classList.add('is-invalid');
            }
        });
        
        if (hasErrors) {
            e.preventDefault();
            showError('Please fix the errors in the form');
        }
    });
} 