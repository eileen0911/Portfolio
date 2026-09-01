// Session Form JavaScript
let selectedMember = null;
let courseTemplate = null;

document.addEventListener('DOMContentLoaded', function () {
    // Get the course item template
    courseTemplate = document.getElementById('courseItemTemplate');

    // Add event listeners
    document.getElementById('member-phone-search').addEventListener('keypress', function (e) {
        if (e.key === 'Enter') {
            searchMember();
        }
    });
});

// Virtual keyboard functions
function addToPhone(digit) {
    const phoneInput = document.getElementById('member-phone-search');
    const currentValue = phoneInput.value;

    if (currentValue.length < 10) {
        const start = phoneInput.selectionStart ?? currentValue.length;
        const end = phoneInput.selectionEnd ?? currentValue.length;
        const newValue = currentValue.slice(0, start) + digit + currentValue.slice(end);
        phoneInput.value = newValue;
        phoneInput.setSelectionRange(start + 1, start + 1);
        phoneInput.focus();
    }
}

function removeFromPhone(action = '') {
    const phoneInput = document.getElementById('member-phone-search');
    const currentValue = phoneInput.value;
    const start = phoneInput.selectionStart ?? currentValue.length;
    const end = phoneInput.selectionEnd ?? currentValue.length;

    if (start !== end) {
        const newValue = currentValue.slice(0, start) + currentValue.slice(end);
        phoneInput.value = newValue;
        phoneInput.setSelectionRange(start, start);
    } else if (start > 0) {
        const newValue = currentValue.slice(0, start - 1) + currentValue.slice(start);
        phoneInput.value = newValue;
        phoneInput.setSelectionRange(start - 1, start - 1);
    }
    phoneInput.focus();
}

function clearPhoneInput(action = '') {
    const phoneInput = document.getElementById('member-phone-search');
    phoneInput.value = '';
    phoneInput.focus();
}

function searchMember() {
    const phoneInput = document.getElementById('member-phone-search');
    const phone = phoneInput.value.trim();

    if (phone.length < 2) {
        alert('請輸入至少2個字符進行搜尋');
        return;
    }

    // Show loading state
    const searchButton = document.querySelector('button[onclick="searchMember()"]');
    const originalText = searchButton.innerHTML;
    searchButton.innerHTML = '<i class="bi bi-hourglass-split"></i> 搜尋中...';
    searchButton.disabled = true;

    // Search for members
    fetch(`/api/members/search/?q=${encodeURIComponent(phone)}`)
        .then(response => response.json())
        .then(data => {
            if (data.length === 0) {
                alert('找不到符合條件的會員');
                return;
            }

            if (data.length === 1) {
                // Auto-select if only one result
                selectMember(data[0]);
            } else {
                // Show multiple results
                showMemberSearchResults(data);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('搜尋會員時發生錯誤，請稍後再試');
        })
        .finally(() => {
            // Restore button state
            searchButton.innerHTML = originalText;
            searchButton.disabled = false;
        });
}

function showMemberSearchResults(members) {
    const resultsContainer = document.getElementById('member-search-results');
    resultsContainer.innerHTML = '';

    members.forEach(member => {
        const resultDiv = document.createElement('div');
        resultDiv.className = 'member-result p-2 border-bottom cursor-pointer';
        resultDiv.innerHTML = `
            <div><strong>${member.name}</strong></div>
            <div class="text-muted small">${member.phone} - ${member.member_code}</div>
        `;
        resultDiv.addEventListener('click', () => selectMember(member));
        resultsContainer.appendChild(resultDiv);
    });

    resultsContainer.style.display = 'block';
}

function selectMember(member) {
    selectedMember = member;

    // Hide search results
    document.getElementById('member-search-results').style.display = 'none';

    // Update member info display
    document.getElementById('member-name').textContent = member.name;
    document.getElementById('member-phone').textContent = member.phone;

    // Show member info section
    document.getElementById('member-info-section').style.display = 'block';

    // Load member's courses and coach info
    loadMemberCourses(member.id);
    loadMemberCoach(member.id);
}

function loadMemberCoach(memberId) {
    // Fetch member details including coach information
    fetch(`/api/members/${memberId}/details/`)
        .then(response => response.json())
        .then(data => {
            if (data.coach_id) {
                // Set the default coach in the dropdown
                const coachSelect = document.getElementById('session-coach-select');
                if (coachSelect) {
                    coachSelect.value = data.coach_id;
                }
            }
        })
        .catch(error => {
            console.error('Error loading coach info:', error);
        });
}

function loadMemberCourses(memberId) {
    // Show course selection section
    document.getElementById('course-selection-section').style.display = 'block';

    // Show loading state
    const courseList = document.getElementById('course-list');
    courseList.innerHTML = '<div class="text-center"><i class="bi bi-hourglass-split"></i> 載入課程中...</div>';

    fetch(`/api/members/${memberId}/courses/`)
        .then(response => response.json())
        .then(data => {
            if (data.length === 0) {
                document.getElementById('no-courses-message').style.display = 'block';
                courseList.innerHTML = '';
            } else {
                displayCourses(data);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            courseList.innerHTML = '<div class="alert alert-danger">載入課程時發生錯誤，請稍後再試</div>';
        });
}

function displayCourses(courses) {
    const courseList = document.getElementById('course-list');
    courseList.innerHTML = '';

    courses.forEach(course => {
        const courseElement = courseTemplate.content.cloneNode(true);

        // Fill in course data
        courseElement.querySelector('.course-name').textContent = course.course_name;
        courseElement.querySelector('.course-code').textContent = course.course_code;
        courseElement.querySelector('.remaining-quantity').textContent = course.remaining_quantity;
        courseElement.querySelector('.order-code').textContent = course.order_code;
        courseElement.querySelector('.order-date').textContent = course.order_date;

        // Store course inventory ID for deduction
        const deductButton = courseElement.querySelector('button[onclick="deductCourse(this)"]');
        deductButton.setAttribute('data-course-inventory-id', course.id);

        courseList.appendChild(courseElement);
    });
}

function deductCourse(button) {
    if (!selectedMember) {
        alert('請先選擇會員');
        return;
    }

    const courseInventoryId = button.getAttribute('data-course-inventory-id');
    const coachId = document.getElementById('session-coach-select').value;

    // Confirm action
    if (!confirm('確定要扣除1堂課嗎？此操作無法復原。')) {
        return;
    }

    // Show loading state
    button.innerHTML = '<i class="bi bi-hourglass-split"></i> 處理中...';
    button.disabled = true;

    // Prepare form data
    const formData = new FormData();
    formData.append('member_id', selectedMember.id);
    formData.append('course_inventory_id', courseInventoryId);
    formData.append('coach_id', coachId);
    formData.append('notes', ''); // No notes field anymore

    // Send request
    fetch('/api/sessions/deduct/', {
        method: 'POST',
        body: formData,
        headers: {
            'X-CSRFToken': getCookie('csrftoken')
        }
    })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showSuccessMessage(data);
            } else {
                alert(data.error || '扣課時發生錯誤，請稍後再試');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('扣課時發生錯誤，請稍後再試');
        })
        .finally(() => {
            // Restore button state
            button.innerHTML = '<i class="bi bi-check"></i> 扣課';
            button.disabled = false;
        });
}

function showSuccessMessage(data) {
    // Hide other sections
    document.getElementById('member-info-section').style.display = 'none';
    document.getElementById('course-selection-section').style.display = 'none';

    // Fill success message
    document.getElementById('success-session-code').textContent = data.session_code;
    document.getElementById('success-member-name').textContent = data.member_name;
    document.getElementById('success-coach-name').textContent = data.coach_name;
    document.getElementById('success-course-name').textContent = data.course_name;
    document.getElementById('success-session-date').textContent = data.session_date;
    document.getElementById('success-order-code').textContent = data.order_code;
    document.getElementById('success-order-date').textContent = data.order_date;

    // Show success section
    document.getElementById('success-message-section').style.display = 'block';
}

function resetForm() {
    // Clear form
    document.getElementById('member-phone-search').value = '';

    // Hide all sections except member search
    document.getElementById('member-info-section').style.display = 'none';
    document.getElementById('course-selection-section').style.display = 'none';
    document.getElementById('success-message-section').style.display = 'none';

    // Clear data
    selectedMember = null;
    document.getElementById('course-list').innerHTML = '';
    document.getElementById('no-courses-message').style.display = 'none';

    // Focus on search input
    document.getElementById('member-phone-search').focus();
}

// Utility function to get CSRF token
function getCookie(name) {
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
