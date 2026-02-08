/**
 * Time Formatters for Volleyball Module
 * 
 * Different formatting style than futsal-nalf
 */

const VolleyballFormatters = {
    /**
     * Volleyball uses compact format by default: 12m 34s
     */
    formatElapsedTime(milliseconds, options = {}) {
        const {
            format = 'compact',         // Default to compact for volleyball
            separator = ' ',
            showTenths = true           // Show tenths of seconds
        } = options;

        const isNegative = milliseconds < 0;
        const absMs = Math.abs(milliseconds);

        const totalSeconds = Math.floor(absMs / 1000);
        const minutes = Math.floor(totalSeconds / 60);
        const seconds = totalSeconds % 60;
        const tenths = Math.floor((absMs % 1000) / 100);

        let formatted = '';

        switch (format) {
            case 'compact':
                // Volleyball style: 12m 34s or 34.5s
                if (minutes > 0) {
                    formatted = `${minutes}m${separator}${seconds}s`;
                } else {
                    formatted = showTenths ? `${seconds}.${tenths}s` : `${seconds}s`;
                }
                break;

            case 'digital':
                // Digital clock style: 12:34
                const m = String(minutes).padStart(2, '0');
                const s = String(seconds).padStart(2, '0');
                formatted = `${m}:${s}`;
                if (showTenths) {
                    formatted += `.${tenths}`;
                }
                break;

            default:
                formatted = `${minutes}m${separator}${seconds}s`;
        }

        return isNegative ? `-${formatted}` : formatted;
    },

    formatLimit(milliseconds, options = {}) {
        return this.formatElapsedTime(milliseconds, options);
    },

    formatRemaining(elapsedMs, limitMs, options = {}) {
        const remaining = limitMs - elapsedMs;
        return this.formatElapsedTime(remaining, options);
    },

    getProgress(elapsedMs, limitMs) {
        if (limitMs === 0) return 0;
        return Math.min(100, (elapsedMs / limitMs) * 100);
    },

    isOvertime(elapsedMs, limitMs) {
        return elapsedMs > limitMs;
    }
};

window.VolleyballFormatters = VolleyballFormatters;
