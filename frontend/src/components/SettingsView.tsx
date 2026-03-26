import { useState, useEffect, useCallback } from 'react';
import { SystemSettings, LLMProvider } from '../types';
import * as api from '../api';

const PROVIDER_OPTIONS: { value: LLMProvider; label: string; icon: string; description: string }[] = [
  {
    value: 'claude',
    label: 'Claude (Anthropic)',
    icon: '🤖',
    description: 'Use your local Claude subscription / API key via the default Anthropic endpoint.',
  },
  {
    value: 'minimax',
    label: 'MiniMax-M2.5',
    icon: '⚡',
    description: 'Use MiniMax\'s Anthropic-compatible endpoint. Requires an API key.',
  },
];

export default function SettingsView() {
  const [settings, setSettings] = useState<SystemSettings>({
    llm_provider: 'claude',
    minimax_api_key: '',
    minimax_base_url: 'https://api.minimax.io/anthropic',
    minimax_model: 'MiniMax-M2.5',
  });
  const [dirty, setDirty] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [showKey, setShowKey] = useState(false);

  const load = useCallback(async () => {
    try {
      const s = await api.fetchSettings();
      setSettings(s);
    } catch (err) {
      console.error('Failed to load settings', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  function patch<K extends keyof SystemSettings>(key: K, value: SystemSettings[K]) {
    setSettings(prev => ({ ...prev, [key]: value }));
    setDirty(true);
    setSaveMsg(null);
  }

  async function save() {
    setSaving(true);
    setSaveMsg(null);
    try {
      const saved = await api.updateSettings(settings);
      setSettings(saved);
      setDirty(false);
      setSaveMsg({ ok: true, text: '✅ Settings saved successfully.' });
    } catch (err: unknown) {
      setSaveMsg({ ok: false, text: `❌ ${err instanceof Error ? err.message : 'Save failed'}` });
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <div className="settings-view"><p className="settings-loading">Loading settings…</p></div>;
  }

  return (
    <div className="settings-view">
      <div className="settings-header">
        <h2>⚙️ System Settings</h2>
        <p className="settings-subtitle">Configure the LLM provider used by the dispatch runner (dispatch-watcher.sh).</p>
      </div>

      {/* ---- LLM Provider ---- */}
      <section className="settings-section">
        <h3>🤖 LLM Provider</h3>
        <p className="settings-hint">Select which AI backend Claude Code dispatches will use.</p>

        <div className="provider-cards">
          {PROVIDER_OPTIONS.map(opt => (
            <button
              key={opt.value}
              className={`provider-card ${settings.llm_provider === opt.value ? 'active' : ''}`}
              onClick={() => patch('llm_provider', opt.value)}
            >
              <span className="provider-icon">{opt.icon}</span>
              <span className="provider-label">{opt.label}</span>
              <span className="provider-desc">{opt.description}</span>
              {settings.llm_provider === opt.value && <span className="provider-check">✓ Active</span>}
            </button>
          ))}
        </div>
      </section>

      {/* ---- MiniMax Config (only shown when minimax is selected) ---- */}
      {settings.llm_provider === 'minimax' && (
        <section className="settings-section minimax-section">
          <h3>⚡ MiniMax Configuration</h3>

          <div className="settings-field">
            <label htmlFor="minimax-key">API Key</label>
            <div className="settings-input-row">
              <input
                id="minimax-key"
                type={showKey ? 'text' : 'password'}
                className="settings-input"
                placeholder="Enter your MiniMax API key…"
                value={settings.minimax_api_key}
                onChange={e => patch('minimax_api_key', e.target.value)}
              />
              <button
                className="toggle-visibility-btn"
                onClick={() => setShowKey(v => !v)}
                title={showKey ? 'Hide key' : 'Show key'}
              >
                {showKey ? '🙈' : '👁️'}
              </button>
            </div>
            {!settings.minimax_api_key && (
              <p className="settings-warn">⚠️ No API key set — dispatches will fall back to native Claude.</p>
            )}
          </div>

          <div className="settings-field">
            <label htmlFor="minimax-url">Base URL</label>
            <input
              id="minimax-url"
              type="text"
              className="settings-input"
              value={settings.minimax_base_url}
              onChange={e => patch('minimax_base_url', e.target.value)}
            />
            <p className="settings-hint-sm">Anthropic-compatible endpoint for MiniMax.</p>
          </div>

          <div className="settings-field">
            <label htmlFor="minimax-model">Model Name</label>
            <input
              id="minimax-model"
              type="text"
              className="settings-input"
              value={settings.minimax_model}
              onChange={e => patch('minimax_model', e.target.value)}
            />
            <p className="settings-hint-sm">e.g. MiniMax-M2.5</p>
          </div>

          <div className="settings-info-box">
            <strong>How it works:</strong> When a dispatch runs, <code>dispatch-watcher.sh</code> reads these settings from the DB and exports:
            <pre>{`ANTHROPIC_BASE_URL="${settings.minimax_base_url}"\nANTHROPIC_API_KEY="<your key>"\nANTHROPIC_MODEL="${settings.minimax_model}"`}</pre>
            before invoking <code>claude --print …</code>
          </div>
        </section>
      )}

      {/* ---- Save ---- */}
      <div className="settings-actions">
        <button
          className={`settings-save-btn ${dirty ? 'dirty' : ''}`}
          onClick={save}
          disabled={saving || !dirty}
        >
          {saving ? '⏳ Saving…' : '💾 Save Settings'}
        </button>
        {saveMsg && (
          <span className={`settings-save-msg ${saveMsg.ok ? 'ok' : 'err'}`}>
            {saveMsg.text}
          </span>
        )}
      </div>
    </div>
  );
}
