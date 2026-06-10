import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import "@reno/graph/styles.css";
import "./styles.css";

createRoot(document.getElementById("root")).render(<App />);
