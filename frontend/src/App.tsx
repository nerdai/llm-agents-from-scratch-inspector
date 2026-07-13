import { useEffect, useState } from "react";
import "./App.css";

/**
 * Placeholder root component.
 *
 * This is a minimal scaffold. The real Agent Inspector UI (session
 * list, step-by-step task driver, rollout viewer, etc.) is built out
 * in a later issue. For now this page simply confirms that the
 * frontend is served correctly and can reach the backend API.
 */
function App() {
  const [health, setHealth] = useState<string>("checking...");

  useEffect(() => {
    fetch("/api/health")
      .then((res) => res.json())
      .then((data) => setHealth(JSON.stringify(data)))
      .catch(() => setHealth("unreachable"));
  }, []);

  return (
    <section id="center">
      <h1>Agent Inspector</h1>
      <p>Frontend scaffold is up and running.</p>
      <p>
        Backend health check: <code>{health}</code>
      </p>
    </section>
  );
}

export default App;
