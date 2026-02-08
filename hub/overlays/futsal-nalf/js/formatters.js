/**
 * Time Formatters for Futsal NALF Module
 * 
 * Provides module-specific time formatting functions.
 * Each main module can have its own formatters.js with custom formats.
 */

const FutsalFormatters = {
    /**
     * Format elapsed time in milliseconds to mm:ss
     * 
     * @param {number} milliseconds - Time in milliseconds
     * @param {object} options - Formatting options
     * @returns {string} Formatted time string
     */
    formatElapsedTime(milliseconds, options = {}) {
        const {
            format = 'mm:ss',           // Default format
            showHours = false,          // Show hours if > 60 minutes
            padZeros = true,            // Pad with zeros (09:05 vs 9:5)
            showMilliseconds = false,   // Show .ms at the end
            separator = ':',            // Time separator
            negativeSign = '-'          // Sign for negative values
        } = options;

        // Handle negative values
        const isNegative = milliseconds < 0;
        const absMs = Math.abs(milliseconds);

        // WZÓR DO ZAIMPLEMENTOWANIA
        // const minutes = Math.floor(elapsedMs / 60000);
        // const seconds = Math.floor((elapsedMs % 60000) / 1000);
        // const dseconds = Math.floor((elapsedMs % 1000) / 100);

        // Calculate time components
        const totalSeconds = Math.floor(absMs / 1000);
        const hours = Math.floor(totalSeconds / 3600);
        const minutes = Math.floor((totalSeconds % 3600) / 60);
        const seconds = totalSeconds % 60;
        const ms = Math.floor((absMs % 1000) / 10); // Two digits for ms

        // Build formatted string based on format
        let formatted = '';

        switch (format) {
            case 'mm:ss':
                // Standard format: 12:34
                const m = padZeros ? String(minutes).padStart(2, '0') : minutes;
                const s = padZeros ? String(seconds).padStart(2, '0') : seconds;
                formatted = `${m}${separator}${s}`;
                break;

            case 'hh:mm:ss':
                // With hours: 01:12:34
                const h = padZeros ? String(hours).padStart(2, '0') : hours;
                const m2 = padZeros ? String(minutes).padStart(2, '0') : minutes;
                const s2 = padZeros ? String(seconds).padStart(2, '0') : seconds;
                formatted = `${h}${separator}${m2}${separator}${s2}`;
                break;

            case 'auto':
                // Auto: show hours only if > 60 minutes
                if (hours > 0 || showHours) {
                    const h = padZeros ? String(hours).padStart(2, '0') : hours;
                    const m2 = padZeros ? String(minutes).padStart(2, '0') : minutes;
                    const s2 = padZeros ? String(seconds).padStart(2, '0') : seconds;
                    formatted = `${h}${separator}${m2}${separator}${s2}`;
                } else {
                    const m = padZeros ? String(minutes).padStart(2, '0') : minutes;
                    const s = padZeros ? String(seconds).padStart(2, '0') : seconds;
                    formatted = `${m}${separator}${s}`;
                }
                break;

            case 'compact':
                // Compact: 12m 34s
                if (hours > 0) {
                    formatted = `${hours}h ${minutes}m ${seconds}s`;
                } else if (minutes > 0) {
                    formatted = `${minutes}m ${seconds}s`;
                } else {
                    formatted = `${seconds}s`;
                }
                break;

            case 'verbose':
                // Verbose: 12 minutes, 34 seconds
                const parts = [];
                if (hours > 0) parts.push(`${hours} ${hours === 1 ? 'hour' : 'hours'}`);
                if (minutes > 0) parts.push(`${minutes} ${minutes === 1 ? 'minute' : 'minutes'}`);
                if (seconds > 0 || parts.length === 0) {
                    parts.push(`${seconds} ${seconds === 1 ? 'second' : 'seconds'}`);
                }
                formatted = parts.join(', ');
                break;

            default:
                // Fallback to mm:ss
                const mDef = padZeros ? String(minutes).padStart(2, '0') : minutes;
                const sDef = padZeros ? String(seconds).padStart(2, '0') : seconds;
                formatted = `${mDef}${separator}${sDef}`;
        }

        // Add milliseconds if requested
        if (showMilliseconds) {
            const msFormatted = String(ms).padStart(2, '0');
            formatted += `.${msFormatted}`;
        }

        // Add negative sign if needed
        if (isNegative) {
            formatted = `${negativeSign}${formatted}`;
        }

        return formatted;
    },

    /**
     * Format timer limit (same as elapsed time)
     */
    formatLimit(milliseconds, options = {}) {
        return this.formatElapsedTime(milliseconds, options);
    },

    /**
     * Format remaining time (limit - elapsed)
     */
    formatRemaining(elapsedMs, limitMs, options = {}) {
        const remaining = limitMs - elapsedMs;
        return this.formatElapsedTime(remaining, options);
    },

    /**
     * Get progress percentage
     */
    getProgress(elapsedMs, limitMs) {
        if (limitMs === 0) return 0;
        return Math.min(100, (elapsedMs / limitMs) * 100);
    },

    /**
     * Check if time limit exceeded
     */
    isOvertime(elapsedMs, limitMs) {
        return elapsedMs > limitMs;
    }
};

// Make available globally
window.FutsalFormatters = FutsalFormatters;
