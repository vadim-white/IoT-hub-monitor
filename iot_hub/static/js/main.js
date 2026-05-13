// Main JavaScript functionality

// Функции для управления устройствами
function viewDeviceMetrics(deviceId, deviceName) {
    document.getElementById('device-name-title').textContent = deviceName;
    document.getElementById('metrics-content').innerHTML = '<p>Загрузка метрик...</p>';
    openModal('metricsModal');
    
    // Загрузить метрики
    fetch(`/api/devices/devices/${deviceId}/`, {
        method: 'GET',
        headers: {'Content-Type': 'application/json'}
    })
    .then(r => r.json())
    .then(data => {
        if (data.metrics && data.metrics.length > 0) {
            let html = '<table class="table"><thead><tr><th>Тип</th><th>Название</th><th>Единица</th><th>Диапазон</th></tr></thead><tbody>';
            data.metrics.forEach(m => {
                const range = m.min_value && m.max_value ? `${m.min_value} - ${m.max_value}` : 'Не установлены';
                html += `
                    <tr>
                        <td>${m.metric_type}</td>
                        <td>${m.name}</td>
                        <td>${m.unit || '-'}</td>
                        <td>${range}</td>
                    </tr>
                `;
            });
            html += '</tbody></table>';
            document.getElementById('metrics-content').innerHTML = html;
        } else {
            document.getElementById('metrics-content').innerHTML = '<p style="text-align: center; color: #999;">Нет метрик для этого устройства</p>';
        }
    })
    .catch(error => {
        console.error('Error:', error);
        document.getElementById('metrics-content').innerHTML = '<p style="color: red;">Ошибка загрузки метрик</p>';
    });
}

function openEditDeviceModal(deviceId, deviceName) {
    // Загрузить данные устройства
    fetch(`/api/devices/devices/${deviceId}/`, {
        method: 'GET',
        headers: {'Content-Type': 'application/json'}
    })
    .then(r => {
        if (!r.ok) {
            throw new Error(`HTTP ${r.status}: Failed to load device`);
        }
        return r.json();
    })
    .then(data => {
        // Заполнить форму
        const idInput = document.getElementById('edit-device-id');
        const nameInput = document.getElementById('edit-device-name');
        const serialInput = document.getElementById('edit-device-serial');
        const typeInput = document.getElementById('edit-device-type');
        const statusInput = document.getElementById('edit-device-status');
        const locationInput = document.getElementById('edit-device-location');
        const descInput = document.getElementById('edit-device-description');
        
        if (idInput) idInput.value = deviceId;
        if (nameInput) nameInput.value = data.name || '';
        if (serialInput) serialInput.value = data.serial_number || '';
        
        // Установить device_type - это ID устройства
        if (typeInput) {
            // data.device_type должен быть ID (число)
            typeInput.value = (data.device_type && typeof data.device_type === 'number') ? data.device_type : '';
            console.log(`Device type set to: ${typeInput.value}`);
        }
        
        if (statusInput) statusInput.value = data.status || 'inactive';
        if (locationInput) locationInput.value = data.location_name || '';
        if (descInput) descInput.value = data.description || '';
        
        // Открыть модальное окно
        openModal('editDeviceModal');
    })
    .catch(error => {
        console.error('Error loading device:', error);
        Toast.error('Ошибка при загрузке данных устройства');
    });
}

function editDevice(deviceId) {
    // Функция для detail.html - просто вызывает openEditDeviceModal
    openEditDeviceModal(deviceId, '');
}

function deleteDevice(deviceId, deviceName) {
    if (confirm(`Вы уверены, что хотите удалить устройство "${deviceName}"?\n\nИстория телеметрии будет сохранена.`)) {
        fetch(`/api/devices/devices/${deviceId}/`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': API.getCookie('csrftoken')
            }
        })
        .then(response => {
            if (response.status === 204 || response.ok) {
                Toast.success(`Устройство "${deviceName}" успешно удалено!`);
                setTimeout(() => window.location.href = '/devices/', 1500);
            } else {
                return response.json().then(data => {
                    throw new Error(data.detail || 'Ошибка при удалении');
                });
            }
        })
        .catch(error => {
            console.error('Error:', error);
            Toast.error(`Ошибка при удалении: ${error.message}`);
        });
    }
}

function showChart(deviceId, deviceName) {
    document.getElementById('chart-title').textContent = `: ${deviceName}`;
    
    // Уничтожить старый график если существует
    if (window.telemetryChart) {
        // Проверить, есть ли метод destroy (объект Chart.js имеет этот метод)
        if (typeof window.telemetryChart.destroy === 'function') {
            window.telemetryChart.destroy();
        }
        window.telemetryChart = null;
    }
    
    // Генерируем рандомные данные для графика
    const generateRandomData = () => {
        const data = [];
        for (let i = 0; i < 12; i++) {
            data.push(Math.floor(Math.random() * 100) + 20);
        }
        return data;
    };
    
    openModal('chartModal');
    
    // Убедимся что canvas существует и пуст
    const canvas = document.getElementById('telemetryChart');
    if (!canvas) {
        Toast.error('Canvas не найден');
        return;
    }
    
    // Получить контекст
    const ctx = canvas.getContext('2d');
    const labels = [];
    const now = new Date();
    
    for (let i = 11; i >= 0; i--) {
        const date = new Date(now);
        date.setHours(date.getHours() - i);
        labels.push(date.getHours().toString().padStart(2, '0') + ':00');
    }
    
    const data1 = generateRandomData();
    const data2 = generateRandomData();
    
    // Создать новый график
    window.telemetryChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Метрика 1 (°C)',
                    data: data1,
                    borderColor: '#3498db',
                    backgroundColor: 'rgba(52, 152, 219, 0.1)',
                    borderWidth: 3,
                    tension: 0.4,
                    fill: true,
                    pointRadius: 4,
                    pointHoverRadius: 6,
                    pointBackgroundColor: '#3498db'
                },
                {
                    label: 'Метрика 2 (%)',
                    data: data2,
                    borderColor: '#e74c3c',
                    backgroundColor: 'rgba(231, 76, 60, 0.1)',
                    borderWidth: 3,
                    tension: 0.4,
                    fill: true,
                    pointRadius: 4,
                    pointHoverRadius: 6,
                    pointBackgroundColor: '#e74c3c'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: {
                        font: { size: 12 },
                        padding: 15
                    }
                },
                title: {
                    display: true,
                    text: `Телеметрия за последние 12 часов - ${deviceName}`,
                    font: { size: 16, weight: 'bold' }
                },
                tooltip: {
                    backgroundColor: 'rgba(0,0,0,0.8)',
                    padding: 12,
                    cornerRadius: 4,
                    titleFont: { size: 13 },
                    bodyFont: { size: 12 }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    max: 120,
                    ticks: {
                        stepSize: 20
                    },
                    grid: {
                        color: 'rgba(0, 0, 0, 0.1)'
                    }
                },
                x: {
                    grid: {
                        display: false
                    }
                }
            }
        }
    });
}

function showSettings(deviceId) {
    Toast.warning('Функция настроек находится в разработке');
}


// Toast Notification System
const Toast = {
    show: function(message, type = 'info', duration = 3000) {
        // Create container if doesn't exist
        if (!document.querySelector('.toast-container')) {
            const container = document.createElement('div');
            container.className = 'toast-container';
            document.body.appendChild(container);
        }
        
        const container = document.querySelector('.toast-container');
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        
        // Icons for different toast types
        const icons = {
            success: '<i class="fas fa-check-circle"></i>',
            error: '<i class="fas fa-times-circle"></i>',
            warning: '<i class="fas fa-exclamation-circle"></i>',
            info: '<i class="fas fa-info-circle"></i>'
        };
        
        toast.innerHTML = `
            <div class="icon">${icons[type] || icons.info}</div>
            <div class="content">
                <p class="message">${message}</p>
            </div>
            <button class="close-btn" onclick="this.closest('.toast').remove()">
                <i class="fas fa-times"></i>
            </button>
        `;
        
        container.appendChild(toast);
        
        // Auto-remove after duration
        if (duration > 0) {
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.classList.add('removing');
                    setTimeout(() => toast.remove(), 300);
                }
            }, duration);
        }
    },
    
    success: function(message, duration = 3000) {
        this.show(message, 'success', duration);
    },
    
    error: function(message, duration = 5000) {
        this.show(message, 'error', duration);
    },
    
    warning: function(message, duration = 4000) {
        this.show(message, 'warning', duration);
    },
    
    info: function(message, duration = 3000) {
        this.show(message, 'info', duration);
    }
};

$(document).ready(function() {
    console.log('IoT Hub Monitor loaded');
    
    // Dropdown menu
    $('.dropdown-toggle').click(function(e) {
        e.preventDefault();
        $(this).siblings('.dropdown-menu').toggle();
    });
    
    // Modal functions
    window.openModal = function(modalId) {
        $(`#${modalId}`).addClass('show');
    };
    
    window.closeModal = function(modalId) {
        $(`#${modalId}`).removeClass('show');
    };
    
    // Close modal when clicking close button or dismiss attribute
    $(document).on('click', '.close, [data-dismiss="modal"]', function() {
        $(this).closest('.modal').removeClass('show');
    });
    
    // Close modal when clicking outside
    $(window).on('click', function(event) {
        if ($(event.target).hasClass('modal')) {
            $(event.target).removeClass('show');
        }
    });
    
    // Add User Button
    $('#add-user-btn').click(function(e) {
        e.preventDefault();
        openModal('addUserModal');
    });
    
    // Add User Form Submission
    $('#add-user-form').on('submit', function(e) {
        e.preventDefault();
        const formData = {
            username: $('#username').val(),
            email: $('#email').val(),
            password: $('#password').val(),
            password2: $('#password2').val(),
            first_name: $('#first_name').val(),
            last_name: $('#last_name').val()
        };
        
        API.post('/api/auth/users/register/', formData)
            .then(response => {
                // Check if user was created successfully
                if (response.id || response.username) {
                    Toast.success(`Пользователь ${response.username} успешно создан!`);
                    closeModal('addUserModal');
                    $('#add-user-form')[0].reset();
                    setTimeout(() => location.reload(), 1500);
                } else if (response.detail || response.message) {
                    // API returned error in response
                    Toast.error(response.detail || response.message);
                } else {
                    // Unknown response format
                    Toast.error('Ошибка при создании пользователя');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                Toast.error('Ошибка при добавлении пользователя');
            });
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
    
    // Add Device Modal handlers
    $('#add-device-btn').click(function(e) {
        e.preventDefault();
        openModal('addDeviceModal');
    });
    
    // Add Device Form Submission
    $('#add-device-form').on('submit', function(e) {
        e.preventDefault();
        
        const deviceTypeVal = $('#device-type').val();
        const deviceTypeInt = parseInt(deviceTypeVal);
        
        // Validate device_type
        if (!deviceTypeVal || isNaN(deviceTypeInt)) {
            Toast.error('Пожалуйста, выберите тип устройства');
            return;
        }
        
        const formData = {
            name: $('#device-name').val(),
            serial_number: $('#device-serial').val(),
            device_type: deviceTypeInt,
            status: $('#device-status').val(),
            location_name: $('#device-location').val()
        };
        
        API.post('/api/devices/devices/', formData)
            .then(response => {
                // Check if device was created successfully
                if (response.id || response.name) {
                    Toast.success(`Устройство ${response.name} успешно добавлено!`);
                    closeModal('addDeviceModal');
                    $('#add-device-form')[0].reset();
                    setTimeout(() => location.reload(), 1500);
                } else if (response.detail || response.message) {
                    // API returned error in response
                    Toast.error(response.detail || response.message);
                } else {
                    // Check for field-specific errors
                    let errorMsg = 'Ошибка при добавлении устройства';
                    if (typeof response === 'object') {
                        const errorFields = Object.keys(response);
                        if (errorFields.length > 0) {
                            errorMsg = errorFields.map(field => `${field}: ${response[field]}`).join('; ');
                        }
                    }
                    Toast.error(errorMsg);
                }
            })
            .catch(error => {
                console.error('Error:', error);
                Toast.error('Ошибка при добавлении устройства');
            });
    });
    
    // Edit Device Form Submission
    $('#edit-device-form').on('submit', function(e) {
        e.preventDefault();
        
        const deviceId = $('#edit-device-id').val();
        const deviceTypeVal = $('#edit-device-type').val();
        const deviceTypeInt = parseInt(deviceTypeVal);
        
        // Validate device_type
        if (!deviceTypeVal || isNaN(deviceTypeInt)) {
            Toast.error('Пожалуйста, выберите тип устройства');
            return;
        }
        
        const formData = {
            name: $('#edit-device-name').val(),
            device_type: deviceTypeInt,
            status: $('#edit-device-status').val(),
            location_name: $('#edit-device-location').val(),
            description: $('#edit-device-description').val()
        };
        
        // PUT request for update
        fetch(`/api/devices/devices/${deviceId}/`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': API.getCookie('csrftoken')
            },
            body: JSON.stringify(formData)
        })
        .then(r => {
            if (!r.ok) {
                return r.json().then(errorData => {
                    throw { status: r.status, data: errorData };
                });
            }
            return r.json();
        })
        .then(response => {
            if (response.id || response.name) {
                Toast.success(`Устройство "${response.name}" успешно обновлено!`);
                closeModal('editDeviceModal');
                setTimeout(() => location.reload(), 1500);
            } else if (response.detail) {
                Toast.error(response.detail);
            } else {
                Toast.error('Ошибка при обновлении устройства');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            if (error.status === 400) {
                const errors = error.data;
                let errorMsg = 'Ошибка валидации: ';
                if (typeof errors === 'object') {
                    errorMsg += Object.values(errors).flat().join(', ');
                } else {
                    errorMsg += error.data.detail || 'Неверные данные';
                }
                Toast.error(errorMsg);
            } else {
                Toast.error('Ошибка при обновлении устройства');
            }
        });
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
        
        // First try to get from DOM input field
        const tokenInput = document.querySelector('[name=csrfmiddlewaretoken]');
        if (tokenInput) {
            return tokenInput.value;
        }
        
        // Then try cookies
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
        return cookieValue || '';
    }
};
