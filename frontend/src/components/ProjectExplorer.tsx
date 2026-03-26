import { useState, useEffect, useCallback, useRef } from 'react';
import { ProjectSummary, FileNode, FileContent, ScaffoldRequest, GitBranchInfo, PrPolicy } from '../types';
import * as api from '../api';

// ---- Helpers ----

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function fileIcon(name: string, isDir: boolean): string {
  if (isDir) return '📁';
  const ext = name.split('.').pop()?.toLowerCase() || '';
  const iconMap: Record<string, string> = {
    py: '🐍', ts: '🔷', tsx: '⚛️', js: '🟨', jsx: '⚛️',
    json: '📋', yml: '⚙️', yaml: '⚙️', sql: '🗃️',
    md: '📝', css: '🎨', html: '🌐', sh: '💻',
    txt: '📄', env: '🔒', example: '📎', toml: '⚙️',
    dockerfile: '🐳', lock: '🔐', gitignore: '🚫',
  };
  if (name.toLowerCase() === 'dockerfile') return '🐳';
  if (name.toLowerCase().startsWith('.env')) return '🔒';
  if (name.toLowerCase() === '.gitignore') return '🚫';
  return iconMap[ext] || '📄';
}

// ---- TreeNode sub-component ----

function TreeNodeItem({
  node,
  projectName,
  depth,
  expandedDirs,
  onToggleDir,
  onFileClick,
  selectedPath,
}: {
  node: FileNode;
  projectName: string;
  depth: number;
  expandedDirs: Set<string>;
  onToggleDir: (path: string) => void;
  onFileClick: (projectName: string, path: string) => void;
  selectedPath: string | null;
}) {
  const isExpanded = expandedDirs.has(node.path);
  const isSelected = selectedPath === node.path;

  return (
    <div>
      <div
        className={`tree-node ${isSelected ? 'selected' : ''} ${node.is_dir ? 'dir' : 'file'}`}
        style={{ paddingLeft: `${12 + depth * 16}px` }}
        onClick={() => {
          if (node.is_dir) {
            onToggleDir(node.path);
          } else {
            onFileClick(projectName, node.path);
          }
        }}
      >
        {node.is_dir && (
          <span className="tree-arrow">{isExpanded ? '▼' : '▶'}</span>
        )}
        <span className="tree-icon">{fileIcon(node.name, node.is_dir)}</span>
        <span className="tree-name">{node.name}</span>
        {!node.is_dir && node.size > 0 && (
          <span className="tree-size">{formatSize(node.size)}</span>
        )}
      </div>
      {node.is_dir && isExpanded && node.children && (
        <div className="tree-children">
          {node.children.map((child) => (
            <TreeNodeItem
              key={child.path}
              node={child}
              projectName={projectName}
              depth={depth + 1}
              expandedDirs={expandedDirs}
              onToggleDir={onToggleDir}
              onFileClick={onFileClick}
              selectedPath={selectedPath}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ---- Main Component ----

export default function ProjectExplorer() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [selectedProject, setSelectedProject] = useState<string | null>(null);
  const [fileTree, setFileTree] = useState<FileNode[]>([]);
  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(new Set());
  const [fileContent, setFileContent] = useState<FileContent | null>(null);
  const [loading, setLoading] = useState(false);
  const [treeLoading, setTreeLoading] = useState(false);
  const [selectedFilePath, setSelectedFilePath] = useState<string | null>(null);

  // Scaffold modal
  const [showScaffold, setShowScaffold] = useState(false);
  const [scaffoldName, setScaffoldName] = useState('');
  const [scaffoldDesc, setScaffoldDesc] = useState('');
  const [scaffoldDb, setScaffoldDb] = useState(true);
  const [scaffoldRedis, setScaffoldRedis] = useState(false);
  const [scaffoldDeps, setScaffoldDeps] = useState('');
  const [scaffoldError, setScaffoldError] = useState('');

  // Delete confirmation
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  // Git branch
  const [branchInfo, setBranchInfo] = useState<GitBranchInfo | null>(null);
  const [branchLoading, setBranchLoading] = useState(false);
  const [branchSwitching, setBranchSwitching] = useState(false);

  // Text selection popup
  const codeBlockRef = useRef<HTMLPreElement>(null);
  const [selectionPopup, setSelectionPopup] = useState<{
    text: string;
    top: number;
    left: number;
  } | null>(null);
  const [taskCreating, setTaskCreating] = useState(false);
  const [taskCreated, setTaskCreated] = useState(false);

  function handleCodeMouseUp() {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || !sel.toString().trim()) {
      // Small delay so click-to-deselect works
      setTimeout(() => {
        if (!window.getSelection()?.toString().trim()) {
          setSelectionPopup(null);
          setTaskCreated(false);
        }
      }, 150);
      return;
    }
    const text = sel.toString().trim();
    if (!text) return;

    const range = sel.getRangeAt(0);
    const rect = range.getBoundingClientRect();
    const containerRect = codeBlockRef.current?.getBoundingClientRect();
    if (!containerRect) return;

    setSelectionPopup({
      text,
      top: rect.top - containerRect.top - 44,
      left: rect.left - containerRect.left + rect.width / 2,
    });
    setTaskCreated(false);
  }

  async function handleCreateTaskFromSelection() {
    if (!selectionPopup || taskCreating) return;
    setTaskCreating(true);
    try {
      const title =
        selectionPopup.text.length > 80
          ? selectionPopup.text.substring(0, 77) + '...'
          : selectionPopup.text;
      const filePath = selectedProject && selectedFilePath
        ? `${selectedProject}/${selectedFilePath}`
        : '';
      const description = filePath
        ? `**Source:** \`${filePath}\`\n\n\`\`\`\n${selectionPopup.text}\n\`\`\``
        : selectionPopup.text;
      await api.createTask({ title, description, status: 'planning' });
      setTaskCreated(true);
      setTimeout(() => {
        setSelectionPopup(null);
        setTaskCreated(false);
        window.getSelection()?.removeAllRanges();
      }, 1200);
    } catch (err) {
      console.error('Failed to create task from selection:', err);
    } finally {
      setTaskCreating(false);
    }
  }

  const loadProjects = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.fetchProjects();
      setProjects(data);
    } catch (err) {
      console.error('Failed to load projects:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  async function loadBranches(name: string) {
    setBranchLoading(true);
    try {
      const info = await api.fetchGitBranches(name);
      setBranchInfo(info);
    } catch {
      // Project may not be a git repo
      setBranchInfo(null);
    } finally {
      setBranchLoading(false);
    }
  }

  async function handleBranchChange(projectName: string, branch: string) {
    if (!branch || branchSwitching) return;
    setBranchSwitching(true);
    try {
      await api.checkoutBranch(projectName, branch);
      // Reload branches and tree after checkout
      await loadBranches(projectName);
      const tree = await api.fetchProjectTree(projectName);
      setFileTree(tree);
      const firstLevelDirs = new Set(tree.filter((n) => n.is_dir).map((n) => n.path));
      setExpandedDirs(firstLevelDirs);
      setFileContent(null);
      setSelectedFilePath(null);
    } catch (err: any) {
      console.error('Branch checkout failed:', err);
      alert(`Checkout failed: ${err.message}`);
    } finally {
      setBranchSwitching(false);
    }
  }

  async function selectProject(name: string) {
    if (selectedProject === name) {
      // Collapse
      setSelectedProject(null);
      setFileTree([]);
      setFileContent(null);
      setSelectedFilePath(null);
      setExpandedDirs(new Set());
      setBranchInfo(null);
      return;
    }

    setSelectedProject(name);
    setFileContent(null);
    setSelectedFilePath(null);
    setTreeLoading(true);
    loadBranches(name);
    try {
      const tree = await api.fetchProjectTree(name);
      setFileTree(tree);
      // Auto-expand first level
      const firstLevelDirs = new Set(tree.filter((n) => n.is_dir).map((n) => n.path));
      setExpandedDirs(firstLevelDirs);
    } catch (err) {
      console.error('Failed to load project tree:', err);
    } finally {
      setTreeLoading(false);
    }
  }

  function toggleDir(path: string) {
    setExpandedDirs((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }

  async function handleFileClick(projectName: string, path: string) {
    setSelectedFilePath(path);
    try {
      const content = await api.fetchFileContent(projectName, path);
      setFileContent(content);
    } catch (err) {
      console.error('Failed to load file:', err);
      setFileContent(null);
    }
  }

  async function handleScaffold() {
    setScaffoldError('');
    const req: ScaffoldRequest = {
      name: scaffoldName.trim(),
      description: scaffoldDesc.trim(),
      include_db: scaffoldDb,
      include_redis: scaffoldRedis,
      python_deps: scaffoldDeps
        .split('\n')
        .map((d) => d.trim())
        .filter(Boolean),
    };

    try {
      await api.scaffoldProject(req);
      setShowScaffold(false);
      setScaffoldName('');
      setScaffoldDesc('');
      setScaffoldDeps('');
      await loadProjects();
      // Auto-select the new project
      setSelectedProject(req.name);
      const tree = await api.fetchProjectTree(req.name);
      setFileTree(tree);
      setExpandedDirs(new Set(tree.filter((n) => n.is_dir).map((n) => n.path)));
    } catch (err: any) {
      setScaffoldError(err.message || 'Failed to scaffold project');
    }
  }

  async function handleDelete(name: string) {
    try {
      await api.deleteProject(name);
      if (selectedProject === name) {
        setSelectedProject(null);
        setFileTree([]);
        setFileContent(null);
      }
      setDeleteTarget(null);
      await loadProjects();
    } catch (err) {
      console.error('Failed to delete project:', err);
    }
  }

  async function handleTogglePrPolicy(name: string, current: PrPolicy) {
    const next: PrPolicy = current === 'require_pr' ? 'direct_commit' : 'require_pr';
    try {
      await api.updateProjectSettings(name, { pr_policy: next });
      setProjects((prev) =>
        prev.map((p) => (p.name === name ? { ...p, pr_policy: next } : p)),
      );
    } catch (err) {
      console.error('Failed to update PR policy:', err);
    }
  }

  return (
    <div className="project-explorer">
      {/* Left sidebar: project list + tree */}
      <div className="pe-sidebar">
        <div className="pe-sidebar-header">
          <h3 className="pe-sidebar-title">📂 Projects</h3>
          <button
            className="pe-new-btn"
            onClick={() => setShowScaffold(true)}
            title="Scaffold a new project"
          >
            + New
          </button>
        </div>

        {loading && <div className="pe-loading">Loading…</div>}

        {!loading && projects.length === 0 && (
          <div className="pe-empty">
            <p>No projects yet.</p>
            <p style={{ fontSize: '13px', color: 'var(--text-dim)' }}>
              Click <strong>+ New</strong> to scaffold one from the template.
            </p>
          </div>
        )}

        <div className="pe-project-list">
          {projects.map((proj) => (
            <div key={proj.name} className="pe-project-item">
              <div
                className={`pe-project-header ${selectedProject === proj.name ? 'active' : ''}`}
                onClick={() => selectProject(proj.name)}
              >
                <div className="pe-project-info">
                  <span className="pe-project-icon">
                    {selectedProject === proj.name ? '📂' : '📁'}
                  </span>
                  <div className="pe-project-meta">
                    <span className="pe-project-name">{proj.name}</span>
                    {proj.description && (
                      <span className="pe-project-desc">{proj.description}</span>
                    )}
                  </div>
                </div>
                <div className="pe-project-badges">
                  <button
                    className={`pe-badge pe-pr-policy ${proj.pr_policy === 'require_pr' ? 'pr-required' : 'direct-commit'}`}
                    title={`PR Policy: ${proj.pr_policy === 'require_pr' ? 'PR Required' : 'Direct Commit'} — click to toggle`}
                    onClick={(e) => {
                      e.stopPropagation();
                      handleTogglePrPolicy(proj.name, proj.pr_policy);
                    }}
                  >
                    {proj.pr_policy === 'require_pr' ? '🔒 PR' : '⚡ Direct'}
                  </button>
                  {proj.has_docker_compose && <span className="pe-badge docker" title="Has docker-compose.yml">🐳</span>}
                  {proj.has_claude_md && <span className="pe-badge claude" title="Has CLAUDE.md">🤖</span>}
                  <span className="pe-badge count" title={`${proj.file_count} files, ${proj.dir_count} folders`}>
                    {proj.file_count}f
                  </span>
                  <button
                    className="pe-delete-btn"
                    onClick={(e) => {
                      e.stopPropagation();
                      setDeleteTarget(proj.name);
                    }}
                    title="Delete project"
                  >
                    🗑️
                  </button>
                </div>
              </div>

              {/* Git branch selector */}
              {selectedProject === proj.name && branchInfo && (
                <div className="pe-branch-selector" onClick={(e) => e.stopPropagation()}>
                  <span className="pe-branch-icon">🌿</span>
                  <select
                    className="pe-branch-dropdown"
                    value={branchInfo.current}
                    onChange={(e) => handleBranchChange(proj.name, e.target.value)}
                    disabled={branchSwitching}
                    title="Switch branch"
                  >
                    {branchInfo.branches.map((b) => (
                      <option key={b} value={b}>
                        {b}{b === branchInfo.current ? ' ✓' : ''}
                      </option>
                    ))}
                  </select>
                  {(branchSwitching || branchLoading) && (
                    <span className="pe-branch-spinner">⏳</span>
                  )}
                </div>
              )}

              {/* File tree */}
              {selectedProject === proj.name && (
                <div className="pe-tree">
                  {treeLoading ? (
                    <div className="pe-loading" style={{ padding: '8px 16px' }}>Loading tree…</div>
                  ) : (
                    fileTree.map((node) => (
                      <TreeNodeItem
                        key={node.path}
                        node={node}
                        projectName={proj.name}
                        depth={0}
                        expandedDirs={expandedDirs}
                        onToggleDir={toggleDir}
                        onFileClick={handleFileClick}
                        selectedPath={selectedFilePath}
                      />
                    ))
                  )}
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Services summary for selected project */}
        {selectedProject && (() => {
          const proj = projects.find((p) => p.name === selectedProject);
          if (!proj || proj.services.length === 0) return null;
          return (
            <div className="pe-services">
              <div className="pe-services-title">Docker Services</div>
              {proj.services.map((svc) => (
                <div key={svc} className="pe-service-item">
                  <span className="pe-service-dot" />
                  {svc}
                </div>
              ))}
            </div>
          );
        })()}
      </div>

      {/* Right panel: file viewer */}
      <div className="pe-content">
        {!fileContent && !selectedProject && (
          <div className="pe-welcome">
            <div className="pe-welcome-icon">🦞</div>
            <h2>Project Explorer</h2>
            <p>Browse and manage your Claude Code projects.</p>
            <p style={{ fontSize: '14px', color: 'var(--text-dim)', marginTop: '8px' }}>
              Select a project from the sidebar or scaffold a new one.
            </p>
          </div>
        )}

        {selectedProject && !fileContent && (
          <div className="pe-welcome">
            <div className="pe-welcome-icon">📂</div>
            <h2>{selectedProject}</h2>
            <p>
              {projects.find((p) => p.name === selectedProject)?.description || 'Select a file from the tree to view its contents.'}
            </p>
          </div>
        )}

        {fileContent && (
          <div className="pe-file-viewer">
            <div className="pe-file-header">
              <div className="pe-file-path">
                <span className="pe-file-icon">{fileIcon(fileContent.name, false)}</span>
                <span>{selectedProject}/{fileContent.path}</span>
              </div>
              <div className="pe-file-meta">
                <span className="pe-file-lang">{fileContent.language}</span>
                <span className="pe-file-size">{formatSize(fileContent.size)}</span>
              </div>
            </div>
            <pre className="pe-code-block" ref={codeBlockRef} onMouseUp={handleCodeMouseUp}>
              <code>{fileContent.content}</code>
              {selectionPopup && (
                <div
                  className="pe-selection-popup"
                  style={{
                    top: selectionPopup.top,
                    left: selectionPopup.left,
                  }}
                  onMouseDown={(e) => e.preventDefault()}
                >
                  {taskCreated ? (
                    <span className="pe-popup-success">✅ Added!</span>
                  ) : (
                    <button
                      className="pe-popup-btn"
                      onClick={handleCreateTaskFromSelection}
                      disabled={taskCreating}
                    >
                      {taskCreating ? '⏳' : '📝'} {taskCreating ? 'Creating...' : 'Add to Planning'}
                    </button>
                  )}
                </div>
              )}
            </pre>
          </div>
        )}
      </div>

      {/* Scaffold Modal */}
      {showScaffold && (
        <div className="modal-overlay" onClick={() => setShowScaffold(false)}>
          <div className="modal-content scaffold-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3 style={{ fontSize: '16px', fontWeight: 600 }}>🛠️ Scaffold New Project</h3>
              <button className="modal-close" onClick={() => setShowScaffold(false)}>✕</button>
            </div>
            <div className="scaffold-form">
              <label className="modal-label">Project Name</label>
              <input
                className="schedule-input"
                value={scaffoldName}
                onChange={(e) => setScaffoldName(e.target.value)}
                placeholder="my-new-api"
                autoFocus
              />

              <label className="modal-label">Description</label>
              <input
                className="schedule-input"
                value={scaffoldDesc}
                onChange={(e) => setScaffoldDesc(e.target.value)}
                placeholder="What does this project do?"
              />

              <div className="scaffold-toggles">
                <label className="scaffold-toggle">
                  <input
                    type="checkbox"
                    checked={scaffoldDb}
                    onChange={(e) => setScaffoldDb(e.target.checked)}
                  />
                  <span>🗃️ PostgreSQL Database</span>
                </label>
                <label className="scaffold-toggle">
                  <input
                    type="checkbox"
                    checked={scaffoldRedis}
                    onChange={(e) => setScaffoldRedis(e.target.checked)}
                  />
                  <span>⚡ Redis Cache</span>
                </label>
              </div>

              <label className="modal-label">Extra Python Deps <span style={{ color: 'var(--text-dim)', fontWeight: 400, fontSize: '12px' }}>(one per line)</span></label>
              <textarea
                className="schedule-input"
                value={scaffoldDeps}
                onChange={(e) => setScaffoldDeps(e.target.value)}
                placeholder={"fastapi\nuvicorn\nhttpx"}
                rows={3}
                style={{ resize: 'vertical' }}
              />

              {scaffoldError && (
                <div className="scaffold-error">⚠️ {scaffoldError}</div>
              )}

              <button
                className="schedule-submit"
                onClick={handleScaffold}
                disabled={!scaffoldName.trim()}
              >
                Create Project
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation */}
      {deleteTarget && (
        <div className="modal-overlay" onClick={() => setDeleteTarget(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ width: '400px' }}>
            <div className="modal-header">
              <h3 style={{ fontSize: '16px', fontWeight: 600 }}>🗑️ Delete Project</h3>
              <button className="modal-close" onClick={() => setDeleteTarget(null)}>✕</button>
            </div>
            <div style={{ padding: '16px 20px 20px' }}>
              <p style={{ marginBottom: '16px', lineHeight: '1.5' }}>
                Are you sure you want to delete <strong>{deleteTarget}</strong>?
                <br />
                <span style={{ color: '#ef4444', fontSize: '13px' }}>This action cannot be undone.</span>
              </p>
              <div style={{ display: 'flex', gap: '12px' }}>
                <button
                  className="schedule-submit"
                  style={{ flex: 1, background: '#ef4444' }}
                  onClick={() => handleDelete(deleteTarget)}
                >
                  Delete
                </button>
                <button
                  className="schedule-submit"
                  style={{ flex: 1, background: 'var(--surface)' }}
                  onClick={() => setDeleteTarget(null)}
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
