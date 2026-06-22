import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';

interface PostmortemViewerProps {
  postmortem: string;
  incidentId: string;
}

const PostmortemViewer: React.FC<PostmortemViewerProps> = ({ postmortem, incidentId }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(postmortem);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    const blob = new Blob([postmortem], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `postmortem-${incidentId.slice(0, 8)}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (!postmortem) {
    return (
      <div className="glass-card p-6">
        <h3 className="text-base font-semibold text-white mb-3">Auto-Generated Postmortem</h3>
        <div className="text-center text-slate-500 py-8 text-sm">
          Postmortem will be generated after analysis completes...
        </div>
      </div>
    );
  }

  return (
    <div className="glass-card p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-base font-semibold text-white">Auto-Generated Postmortem</h3>
        <div className="flex items-center gap-2">
          <button
            id={`btn-copy-postmortem-${incidentId}`}
            onClick={handleCopy}
            className="btn-ghost text-xs px-3 py-1.5"
          >
            {copied ? '✓ Copied!' : 'Copy'}
          </button>
          <button
            id={`btn-download-postmortem-${incidentId}`}
            onClick={handleDownload}
            className="btn-primary text-xs px-3 py-1.5"
          >
            ↓ Download .md
          </button>
        </div>
      </div>

      <div
        className="max-h-96 overflow-y-auto rounded-xl bg-black/30 border border-slate-700/50 p-5"
        style={{ fontFamily: "'Inter', sans-serif" }}
      >
        <ReactMarkdown
          components={{
            h1: ({ children }) => (
              <h1 className="text-xl font-bold text-white mb-4 mt-2 gradient-text">{children}</h1>
            ),
            h2: ({ children }) => (
              <h2 className="text-base font-bold text-blue-300 mb-2 mt-5 border-b border-blue-500/20 pb-1">
                {children}
              </h2>
            ),
            h3: ({ children }) => (
              <h3 className="text-sm font-semibold text-slate-200 mb-1 mt-3">{children}</h3>
            ),
            p: ({ children }) => (
              <p className="text-sm text-slate-300 mb-2 leading-relaxed">{children}</p>
            ),
            li: ({ children }) => (
              <li className="text-sm text-slate-300 ml-4 mb-1 list-disc">{children}</li>
            ),
            strong: ({ children }) => (
              <strong className="font-semibold text-white">{children}</strong>
            ),
            code: ({ children }) => (
              <code className="font-mono text-xs bg-black/40 text-cyan-300 px-1.5 py-0.5 rounded">
                {children}
              </code>
            ),
            hr: () => <hr className="border-slate-700/50 my-3" />,
          }}
        >
          {postmortem}
        </ReactMarkdown>
      </div>
    </div>
  );
};

export default PostmortemViewer;
