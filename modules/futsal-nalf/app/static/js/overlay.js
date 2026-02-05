/**
 * OVERLAY JAVASCRIPT - For OBS Browser Source
 * Connects to Flask server and updates overlay in real-time
 */

// Connect to Flask server (adjust URL if needed)
const socket = io('http://localhost:8081');

// ============================================
// CONNECTION
// ============================================

socket.on('connect', () => {
    console.log('✅ Overlay connected to server');
});

socket.on('disconnect', () => {
    console.log('❌ Overlay disconnected from server');
});

// ============================================
// MATCH UPDATES (for scoreboard)
// ============================================

socket.on('match_updated', (data) => {
    console.log('Match updated:', data);
    updateScoreboard(data);
});

socket.on('match_started', (data) => {
    console.log('Match started:', data);
    updateScoreboard(data);
});

socket.on('goal_scored', (data) => {
    console.log('Goal scored:', data);
    if (data.score) {
        updateScoreboard(data);
    }
});

function updateScoreboard(data) {
    const scoreEl = document.getElementById('score');
    
    if (scoreEl && data.score) {
        const homeScore = data.score.home || 0;
        const awayScore = data.score.away || 0;
        scoreEl.textContent = `${homeScore} - ${awayScore}`;
        
        // Optional: Add flash animation
        scoreEl.style.animation = 'none';
        setTimeout(() => {
            scoreEl.style.animation = 'pulse 0.5s ease';
        }, 10);
    }
}

// ============================================
// TIMER UPDATES (for timer overlay)
// ============================================

socket.on('timer_updated', (data) => {
    updateTimer(data);
});

socket.on('timer_started', (data) => {
    setTimerState('running');
});

socket.on('timer_stopped', (data) => {
    setTimerState('stopped');
});

socket.on('timer_state_changed', (data) => {
    if (data.timer && data.timer.state) {
        setTimerState(data.timer.state);
    }
    if (data.timer && data.timer.elapsed_time !== undefined) {
        updateTimer({ elapsed_time: data.timer.elapsed_time });
    }
});

function updateTimer(data) {
    const timerEl = document.getElementById('timer-display');
    
    if (timerEl && data.elapsed_time !== undefined) {
        const minutes = Math.floor(data.elapsed_time / 60000);
        const seconds = Math.floor((data.elapsed_time % 60000) / 1000);
        const ms = Math.floor((data.elapsed_time % 1000) / 10); // centiseconds
        
        timerEl.textContent = `${pad(minutes)}:${pad(seconds)}.${pad(ms)}`;
    }
}

function setTimerState(state) {
    const timerEl = document.getElementById('timer-display');
    
    if (timerEl) {
        timerEl.className = `timer-overlay ${state}`;
    }
}

// ============================================
// PLAYER STATS (for player stats overlay)
// ============================================

socket.on('player_stats_update', (data) => {
    updatePlayerStats(data);
});

function updatePlayerStats(data) {
    // Update individual stat elements
    for (const [key, value] of Object.entries(data)) {
        const statEl = document.getElementById(`stat-${key}`);
        if (statEl) {
            statEl.textContent = value;
        }
    }
}

// ============================================
// UTILITY FUNCTIONS
// ============================================

function pad(num) {
    return String(num).padStart(2, '0');
}

function formatTime(ms) {
    const minutes = Math.floor(ms / 60000);
    const seconds = Math.floor((ms % 60000) / 1000);
    return `${pad(minutes)}:${pad(seconds)}`;
}

// ============================================
// INITIALIZATION
// ============================================

document.addEventListener('DOMContentLoaded', () => {
    console.log('🎬 Overlay initialized');
    
    // Request initial state
    socket.emit('request_current_state');
});