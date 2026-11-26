import { createRoot } from "react-dom/client";
import "@fontsource/barlow/latin-400.css";
import "@fontsource/barlow/latin-500.css";
import "@fontsource/barlow/latin-600.css";
import "@fontsource/barlow-condensed/latin-500.css";
import "@fontsource/barlow-condensed/latin-600.css";
import "@fontsource/barlow-condensed/latin-700.css";
import "@fontsource/doto/latin-700.css";
import "@fontsource/doto/latin-900.css";
import "leaflet/dist/leaflet.css";
import "./style.css";
import { Component } from "react";
import App from "./App.jsx";

// A rendering error must never leave a blank screen in front of the judges.
class Guard extends Component {
  state = { err: null };
  static getDerivedStateFromError(err) { return { err }; }
  render() {
    if (!this.state.err) return this.props.children;
    return (
      <div className="crash" role="alert">
        <h1>Something on this screen failed to draw.</h1>
        <p>{String(this.state.err.message || this.state.err)}</p>
        <button onClick={() => location.reload()}>Reload the screen</button> <a href="/classic">Open the classic page</a>
      </div>
    );
  }
}

createRoot(document.getElementById("root")).render(<Guard><App /></Guard>);
