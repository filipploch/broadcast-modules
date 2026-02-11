/**
 * FUTSAL NALF - Main JavaScript
 * WebSocket communication and UI interactions
 */

// ============================================
// SOCKET.IO CONNECTION
// ============================================

const socket = io();

// Connection handlers
socket.on('connect', () => {
    console.log('✅ Connected to server');
    updateConnectionStatus(true);
});

socket.on('disconnect', () => {
    console.log('❌ Disconnected from server');
    updateConnectionStatus(false);
});

socket.on('connected', (data) => {
    console.log('Server confirmed connection:', data);
});

// ============================================
// PLUGIN STATUS UPDATES
// ============================================

//socket.on('plugin_status', (data) => {
//    console.log('Plugin status update:', data);
//    updatePluginStatus(data.plugin_id, data.status);
//});

//socket.on('plugins_status', (data) => {
//    console.log('All plugins status:', data);
//    updateAllPlugins(data.plugins);
//});

// ============================================
// RECORDING EVENTS
// ============================================

socket.on('recording_started', (data) => {
    console.log('🔴 Recording started:', data);
    showNotification('Recording started', 'success');
    updateRecordingUI(true);
});

socket.on('recording_stopped', (data) => {
    console.log('⏹️ Recording stopped:', data);
    showNotification('Recording stopped', 'info');
    updateRecordingUI(false);
});

// ============================================
// MATCH EVENTS
// ============================================

socket.on('match_started', (data) => {
    console.log('🎮 Match started:', data);
    showNotification('Match started!', 'success');
    updateMatchUI(data);
});

socket.on('match_updated', (data) => {
    console.log('⚽ Match updated:', data);
    updateMatchUI(data);
});

socket.on('match_finished', (data) => {
    console.log('🏁 Match finished:', data);
    showNotification('Match finished!', 'info');
    updateMatchUI(data);
});

// ============================================
// OBS EVENTS
// ============================================

socket.on('scene_changed', (data) => {
    console.log('📹 Scene changed:', data);
    showNotification(`Scene: ${data.scene_name}`, 'info');
});

// ============================================
// TIMER EVENTS
// ============================================

//socket.on('timer_updated', (data) => {
//    // Update timer display
//    updateTimerDisplay(data);
//});



// ============================================
// ERROR HANDLING
// ============================================

socket.on('error', (data) => {
    console.error('Error from server:', data);
    showNotification(data.message || 'An error occurred', 'error');
});

// ============================================
// CONTROL FUNCTIONS
// ============================================

function startRecording() {
    console.log('Starting recording...');
    socket.emit('start_recording');
}

function stopRecording() {
    console.log('Stopping recording...');
    socket.emit('stop_recording');
}

function goalHome() {
    console.log('Goal for home team!');
    socket.emit('goal_scored', { team: 'home' });
}

function goalAway() {
    console.log('Goal for away team!');
    socket.emit('goal_scored', { team: 'away' });
}

function startMatch() {
    console.log('Starting match...');
    socket.emit('start_game');
}

function finishMatch() {
    console.log('Finishing match...');
    socket.emit('finish_game');
}

function changeScene(sceneName) {
    console.log(`Changing scene to: ${sceneName}`);
    socket.emit('change_scene', { scene_name: sceneName });
}



// ============================================
// UI UPDATE FUNCTIONS
// ============================================

function updateConnectionStatus(isConnected) {
    const statusEl = document.getElementById('connection-status');
    if (statusEl) {
        statusEl.textContent = isConnected ? 'Connected' : 'Disconnected';
        statusEl.className = isConnected ? 'status-online' : 'status-offline';
    }
}

//function updatePluginStatus(pluginId, status) {
//    const pluginEl = document.querySelector(`[data-plugin-id="${pluginId}"]`);
//    if (pluginEl) {
//        const statusEl = pluginEl.querySelector('.plugin-status');
//        if (statusEl) {
//            statusEl.textContent = status;
//            statusEl.className = `plugin-status status-${status}`;
//        }
//
//        // Update card styling
//        pluginEl.classList.remove('online', 'offline', 'starting');
//        pluginEl.classList.add(status);
//    }
//}

//function updateAllPlugins(plugins) {
//    plugins.forEach(plugin => {
//        updatePluginStatus(plugin.id, plugin.status);
//    });
//}

function updateRecordingUI(isRecording) {
    const startBtn = document.getElementById('btn-start-recording');
    const stopBtn = document.getElementById('btn-stop-recording');
    
    if (startBtn && stopBtn) {
        startBtn.disabled = isRecording;
        stopBtn.disabled = !isRecording;
    }
}

function updateMatchUI(matchData) {
    // Update score display
    const homeScoreEl = document.getElementById('score-home');
    const awayScoreEl = document.getElementById('score-away');
    
    if (homeScoreEl && matchData.score) {
        homeScoreEl.textContent = matchData.score.home || 0;
    }
    
    if (awayScoreEl && matchData.score) {
        awayScoreEl.textContent = matchData.score.away || 0;
    }
}

function updateTimerDisplay(data) {
    const timerEl = document.getElementById('timer-display');
    if (timerEl && data.elapsed_time !== undefined) {
        const minutes = Math.floor(data.elapsed_time / 60000);
        const seconds = Math.floor((data.elapsed_time % 60000) / 1000);
        timerEl.textContent = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
    }
}

// function updateTimerUI(state) {
//     const timerEl = document.getElementById('timer-display');
//     if (timerEl) {
//         timerEl.setAttribute('data-state', state);
//     }
// }

// ============================================
// NOTIFICATIONS
// ============================================

function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `alert alert-${type}`;
    notification.textContent = message;
    
    const container = document.getElementById('notifications');
    if (container) {
        container.appendChild(notification);
        
        // Auto-remove after 3 seconds
        setTimeout(() => {
            notification.remove();
        }, 3000);
    } else {
        // Fallback to console if no container
        console.log(`[${type.toUpperCase()}] ${message}`);
    }
}

// ============================================
// INITIALIZATION
// ============================================

document.addEventListener('DOMContentLoaded', () => {
    console.log('🚀 App initialized');
    
    // Request initial plugin status
    socket.emit('request_plugin_status');
    
    // Setup button handlers if they exist
    setupButtonHandlers();
});

function setupButtonHandlers() {
    // Recording buttons
    const startRecBtn = document.getElementById('btn-start-recording');
    const stopRecBtn = document.getElementById('btn-stop-recording');
    
    if (startRecBtn) startRecBtn.addEventListener('click', startRecording);
    if (stopRecBtn) stopRecBtn.addEventListener('click', stopRecording);
    
    // Goal buttons
    const goalHomeBtn = document.getElementById('btn-goal-home');
    const goalAwayBtn = document.getElementById('btn-goal-away');
    
    if (goalHomeBtn) goalHomeBtn.addEventListener('click', goalHome);
    if (goalAwayBtn) goalAwayBtn.addEventListener('click', goalAway);
    
    // Match buttons
    const startMatchBtn = document.getElementById('btn-start-match');
    const finishMatchBtn = document.getElementById('btn-finish-match');
    
    if (startMatchBtn) startMatchBtn.addEventListener('click', startMatch);
    if (finishMatchBtn) finishMatchBtn.addEventListener('click', finishMatch);
    
    // Timer buttons
    const startTimerBtn = document.getElementById('btn-start-timer');
    const stopTimerBtn = document.getElementById('btn-stop-timer');
    const resetTimerBtn = document.getElementById('btn-reset-timer');
    
    if (startTimerBtn) startTimerBtn.addEventListener('click', startTimer);
    if (stopTimerBtn) stopTimerBtn.addEventListener('click', stopTimer);
    if (resetTimerBtn) resetTimerBtn.addEventListener('click', resetTimer);
}

// ============================================
// UTILITY FUNCTIONS
// ============================================

function formatTime(milliseconds) {
    const minutes = Math.floor(milliseconds / 60000);
    const seconds = Math.floor((milliseconds % 60000) / 1000);
    const ms = milliseconds % 1000;
    
    return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}.${String(ms).padStart(3, '0')}`;
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Export functions for use in HTML onclick handlers
window.startRecording = startRecording;
window.stopRecording = stopRecording;
window.goalHome = goalHome;
window.goalAway = goalAway;
window.startMatch = startMatch;
window.finishMatch = finishMatch;
window.changeScene = changeScene;
// window.startTimer = startTimer;
// window.stopTimer = stopTimer;
// window.resetTimer = resetTimer;