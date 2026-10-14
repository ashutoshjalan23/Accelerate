import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { request } from "./api.js";
import "./styles.css";

const API_URL = import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`;
const api = (path, options) => request(API_URL, path, options);

function Commands({ title, commands }) {
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);
  const text = commands.join("\n");
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setCopyError(false);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopyError(true);
    }
  }
  return <div className="commands">
    <div className="command-heading"><span>{title}</span><button onClick={copy}>{copied ? "Copied ✓" : "Copy commands"}</button></div>
    <pre><code>{text}</code></pre>
    {copyError && <p className="copy-error">Select the commands and copy them manually.</p>}
  </div>;
}

function Notes({ title, items }) {
  if (!items?.length) return null;
  return <section className="notes"><h3>{title}</h3><ul>{items.map((item, index) => <li key={index}>{item}</li>)}</ul></section>;
}

function App() {
  const [repository, setRepository] = useState("");
  const [cacheOnly, setCacheOnly] = useState(true);
  const [challenges, setChallenges] = useState([]);
  const [active, setActive] = useState(null);
  const [solution, setSolution] = useState(null);
  const [showSolution, setShowSolution] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function loadChallenges() {
    const data = await api("/challenges?limit=20");
    setChallenges(data.items);
  }
  useEffect(() => { loadChallenges().catch(error => setError(error.message)); }, []);

  function select(challenge) {
    setActive(challenge);
    setSolution(null);
    setShowSolution(false);
    setError("");
    setNotice("");
  }

  async function generate(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setNotice(cacheOnly ? "Opening a saved challenge…" : "Finding an engineering challenge. This may take several minutes…");
    try {
      const data = await api("/challenges/generate", {
        method: "POST",
        body: JSON.stringify({ github_url: repository.trim(), use_cache: true, cache_only: cacheOnly }),
      });
      select(data.challenge);
      setNotice(data.cached ? "Opened from cache. No model calls." : "Challenge ready. Work in your local checkout.");
      await loadChallenges();
    } catch (error) {
      setError(error.message);
      setNotice("");
    } finally {
      setLoading(false);
    }
  }

  async function reveal() {
    if (showSolution) { setShowSolution(false); return; }
    setError("");
    setLoading(true);
    try {
      const data = solution || await api(`/challenges/${active.id}/solution`);
      setSolution(data);
      setShowSolution(true);
    } catch (error) {
      setError(error.message);
    } finally {
      setLoading(false);
    }
  }

  const problem = active?.problem;
  const workspace = active?.workspace;
  return <div className="shell">
    <header><button className="brand" onClick={() => { setActive(null); setNotice(""); setError(""); }}><span className="brand-icon">↗</span> accelerate<span className="brand-dot">.</span></button><span className="header-note">Real repositories. Your environment.</span></header>
    <main>
      {!active ? <>
        <section className="intro">
          <p className="eyebrow">A SMALL CHANGE. A REAL ENGINEERING LESSON.</p>
          <h1>Take the challenge.<br /><span>Keep your own tools.</span></h1>
          <p className="intro-copy">Discover an issue from an open-source commit. Check out the code before the fix, work locally, then compare your approach with the maintainers.</p>
          <form onSubmit={generate}>
            <label htmlFor="repository">GitHub repository</label>
            <div className="input-row"><input id="repository" value={repository} onChange={event => setRepository(event.target.value)} placeholder="https://github.com/pallets/flask" required disabled={loading} /><button className="primary" disabled={loading || !repository.trim()}>{loading ? "Working…" : "Get a challenge ↗"}</button></div>
            <label className="cache-toggle"><input type="checkbox" checked={cacheOnly} onChange={event => setCacheOnly(event.target.checked)} disabled={loading} /> Use saved challenges only <span>— no model calls</span></label>
            {!cacheOnly && <p className="generation-note">Reuses saved results first. New repositories use Gemini, with OpenRouter fallback.</p>}
          </form>
        </section>
        {error && <div className="alert" role="alert">{error}<button disabled={loading} onClick={() => { setError(""); loadChallenges().catch(error => setError(error.message)); }}>Retry library</button></div>}
        {notice && <p className="notice" role="status">{notice}</p>}
        <section className="library">
          <div className="section-heading"><h2>Ready to explore</h2><span>{challenges.length} saved challenges</span></div>
          {challenges.length ? <div className="cards">{challenges.map(challenge => <button className="card" key={challenge.id} disabled={loading} onClick={() => select(challenge)}><span className="repo-label">{challenge.repository}<span>↗</span></span><h3>{challenge.problem.title}</h3><p>{challenge.problem.description}</p><span className="card-bottom">{challenge.workspace.relevant_directories.join(" · ")}</span></button>)}</div> : <div className="empty"><h3>Your next lesson starts with a repository.</h3><p>Load the cached demos with <code>python -m app.seed_cached --demo</code>, or turn off saved-only mode to generate a challenge.</p></div>}
        </section>
      </> : <>
        <button className="back" disabled={loading} onClick={() => { setActive(null); setNotice(""); setError(""); }}>← All challenges</button>
        {error && <div className="alert" role="alert">{error}</div>}
        {notice && <p className="notice" role="status">{notice}</p>}
        <div className="challenge-heading"><p className="eyebrow">{active.repository}</p><h1>{problem.title}</h1><p className="base-label">Starting revision <code>{workspace.base_sha.slice(0, 12)}</code> · before the maintainer’s change</p></div>
        <div className="challenge-layout">
          <article>
            <section><h2><span className="step">01</span> The challenge</h2><div className="description">{problem.description.split(/\n\s*\n/).map((paragraph, index) => <p key={index}>{paragraph}</p>)}</div><Notes title="Acceptance criteria" items={problem.acceptance_criteria} /><Notes title="Constraints" items={problem.constraints} /></section>
            <section className="checkout"><h2><span className="step">02</span> Make it yours</h2><p>Run these commands in a terminal to create a fresh checkout at the starting revision. If that folder already exists, choose a different folder name.</p><Commands title="Local checkout" commands={workspace.checkout_commands} /><Notes title="Set up your environment" items={problem.setup_notes} /><Notes title="Check your work" items={problem.verification_notes} /><p className="helper">Use the repository’s tools and tests. Accelerate does not run or grade your code.</p></section>
            <section className="compare"><h2><span className="step">03</span> Compare approaches</h2><p>Inspect your changes locally. For new files, run <code>git add -N &lt;new-file&gt;</code> first so they appear in the diff.</p><Commands title="Your changes against the starting revision" commands={[workspace.local_diff_command]} /><p>When you’re ready, reveal the original change and compare its behavior and trade-offs with yours.</p><button className="reveal" disabled={loading} onClick={reveal}>{loading ? "Loading…" : showSolution ? "Hide maintainer solution ↑" : "Reveal maintainer solution ↓"}</button>
              {showSolution && solution && <div className="solution"><a href={solution.commit_url} target="_blank" rel="noreferrer">View original commit on GitHub ↗</a><p>{solution.message}</p><Commands title="Inspect both patches locally" commands={solution.comparison_commands} /><p className="helper">{solution.note}</p><pre className="diff"><code>{solution.diff}</code></pre></div>}
            </section>
          </article>
          <aside><h3>Where to work</h3><p className="helper">Start with these directories and files. Explore the rest of the repository as needed.</p><ul className="directories">{workspace.relevant_directories.map(path => <li key={path}><span>⌁</span><code>{path === "." ? "Repository root" : path + "/"}</code></li>)}</ul><div className="file-links">{workspace.files.map(file => file.url ? <a href={file.url} key={file.path} target="_blank" rel="noreferrer">{file.path}<span>↗</span></a> : <p className="helper" key={file.path}>{file.path} · new file</p>)}</div><a className="repository-link" href={workspace.repository_url} target="_blank" rel="noreferrer">Open repository ↗</a><p className="helper">File links show the starting revision. The original fix stays behind the reveal button.</p></aside>
        </div>
      </>}
    </main>
    <footer><span>accelerate.</span><span>Learn from the work behind the software.</span></footer>
  </div>;
}

createRoot(document.getElementById("root")).render(<App />);
