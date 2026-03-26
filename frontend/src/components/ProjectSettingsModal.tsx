import { useState, useEffect } from 'react';
import { GitStrategy, ProjectSettingsData } from '../types';
import * as api from '../api';

interface Props {
  projectKey: string;
  onClose: () => void;
  onSaved: (settings: ProjectSettingsData) => void;
}

export default function ProjectSettingsModal({ projectKey, onClose, onSaved }: Props) {
  const [gitStrategy, setGitStrategy] = useState<GitStrategy>('direct_commit');
  const [defaultBranch, setDefaultBranch] = useState('main');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    api.fetchProjectSettings(projectKey).then((s) => {
      setGitStrategy(s.git_strategy);
      setDefaultBranch(s.default_branch);
      setLoaded(true);
    }).catch(() => setLoaded(true));
  }, [projectKey]);

  async function handleSave() {
    setSaving(true);
    setError('');
    try {
      const result = await api.updateProjectGitStrategy(projectKey, {
        git_strategy: gitStrategy,
        default_branch: defaultBranch,
      });
      onSaved(result);
      onClose();
    } catch (err: any) {
      setError(err.message || 'Failed to save');
    } finally {
      setSaving(false);
    }
  }

  if (!loaded) return null;

  return (
    <div className="dispatch-form-overlay" onClick={onClose}>
      <div className="dispatch-form" onClick={(e) => e.stopPropagation()} style={{ width: '440px' }}>
        <div className="dispatch-form-header">
          <h3>Project Settings</h3>
          <button className="modal-close" onClick={onClose}>&#x2715;</button>
        </div>

        <div className="dispatch-form-body">
          <label className="modal-label">Git Strategy</label>
          <div className="dispatch-mode-buttons">
            <button
              className={`dispatch-mode-btn ${gitStrategy === 'direct_commit' ? 'active' : ''}`}
              onClick={() => setGitStrategy('direct_commit')}
              style={gitStrategy === 'direct_commit' ? { borderColor: '#22c55e', background: 'rgba(34, 197, 94, 0.08)' } : {}}
            >
              Direct Commit
              <small>Push directly to the main branch</small>
            </button>
            <button
              className={`dispatch-mode-btn ${gitStrategy === 'pull_request' ? 'active' : ''}`}
              onClick={() => setGitStrategy('pull_request')}
              style={gitStrategy === 'pull_request' ? { borderColor: '#8b5cf6', background: 'rgba(139, 92, 246, 0.08)' } : {}}
            >
              Pull Request
              <small>Create feature branch + PR</small>
            </button>
          </div>

          <label className="modal-label">Default Branch</label>
          <input
            className="schedule-input"
            value={defaultBranch}
            onChange={(e) => setDefaultBranch(e.target.value)}
            placeholder="main"
            style={{ fontFamily: 'monospace', fontSize: '13px' }}
          />

          {error && (
            <div className="scaffold-error">{error}</div>
          )}

          <button
            className="schedule-submit"
            onClick={handleSave}
            disabled={saving || !defaultBranch.trim()}
            style={{ marginTop: '8px' }}
          >
            {saving ? 'Saving...' : 'Save Settings'}
          </button>
        </div>
      </div>
    </div>
  );
}
