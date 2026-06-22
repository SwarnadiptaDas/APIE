/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          900: '#0a0e1a',
          800: '#0f1629',
          700: '#151e38',
          600: '#1e2d52',
          500: '#2a3f6f',
          400: '#3b5998',
          300: '#5b80d4',
          200: '#93b4f0',
          100: '#d4e4ff',
        },
        critical: { DEFAULT: '#ef4444', dark: '#991b1b', light: '#fca5a5' },
        warning: { DEFAULT: '#f59e0b', dark: '#92400e', light: '#fde68a' },
        success: { DEFAULT: '#22c55e', dark: '#14532d', light: '#bbf7d0' },
        info: { DEFAULT: '#3b82f6', dark: '#1e3a8a', light: '#bfdbfe' },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      animation: {
        'pulse-slow': 'pulse 3s ease-in-out infinite',
        'slide-up': 'slideUp 0.3s ease-out',
        'fade-in': 'fadeIn 0.5s ease-out',
        'glow': 'glow 2s ease-in-out infinite alternate',
      },
      keyframes: {
        slideUp: {
          '0%': { transform: 'translateY(20px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        glow: {
          '0%': { boxShadow: '0 0 5px rgba(59,130,246,0.3)' },
          '100%': { boxShadow: '0 0 20px rgba(59,130,246,0.8)' },
        },
      },
    },
  },
  plugins: [],
}
