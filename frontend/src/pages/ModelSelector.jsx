// components/ModelSelector.jsx
// Drop-in model switcher — used in ReadChat and Chat overlays

export const MODELS = [
  { id: 'auto',   label: 'Auto',            icon: '⚡' },
  { id: 'groq',   label: 'Groq · Llama 3.3', icon: '🚀' },
  { id: 'openai', label: 'GPT-4o-mini',      icon: '🧠' },
]

export default function ModelSelector({ value, onChange, style = {} }) {
  return (
    <div className="model-selector" style={style}>
      <span className="model-selector-label">Model</span>
      <select
        className="model-select"
        value={value}
        onChange={e => onChange(e.target.value)}
      >
        {MODELS.map(m => (
          <option key={m.id} value={m.id}>
            {m.icon} {m.label}
          </option>
        ))}
      </select>
    </div>
  )
}