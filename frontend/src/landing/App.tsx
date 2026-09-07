import {
  useEffect,
  useState,
  type CSSProperties,
  type ComponentType,
} from "react";
import {
  Activity,
  ArrowDownRight,
  ArrowRight,
  BarChart3,
  Code2,
  Moon,
  Orbit,
  Sun,
  TrendingUp,
  Clock,
  BarChart2,
} from "lucide-react";

type IconComponent = ComponentType<{ size?: number; strokeWidth?: number }>;

const capabilities: { icon: IconComponent; title: string; body: string }[] = [
  {
    icon: TrendingUp,
    title: "Intelligent Driver Model",
    body: "Vehicle acceleration, braking and gap-keeping follow IDM car-following physics — not scripted motion.",
  },
  {
    icon: Clock,
    title: "Dual control strategies",
    body: "Run the same demand through fixed-time signals and a roundabout, side by side, under identical conditions.",
  },
  {
    icon: BarChart2,
    title: "Real-time visualization",
    body: "Watch every vehicle move through the network as the simulation runs, not just the summary afterward.",
  },
  {
    icon: BarChart3,
    title: "Comprehensive analytics",
    body: "Ten metrics spanning efficiency, flow, system load, fairness and physical constraints — logged per run.",
  },
];

const buildings = [
  { w: "10%", h: "20%", x: "10%", y: "10%" },
  { w: "13%", h: "28%", x: "23%", y: "8%" },
  { w: "10%", h: "17%", x: "73%", y: "9%" },
  { w: "14%", h: "25%", x: "83%", y: "15%" },
  { w: "13%", h: "24%", x: "8%", y: "70%" },
  { w: "9%", h: "17%", x: "22%", y: "78%" },
  { w: "14%", h: "23%", x: "72%", y: "73%" },
  { w: "10%", h: "18%", x: "86%", y: "67%" },
];

const metricGroups = [
  {
    title: "Efficiency",
    metrics: [
      { name: "Average delay", value: "8.4 s", width: "82%", tone: "cyan" },
      {
        name: "Travel time index",
        value: "1.08",
        width: "76%",
        tone: "orange",
      },
      { name: "Fuel consumption", value: "−14.2%", width: "70%", tone: "cyan" },
    ],
  },
  {
    title: "Traffic flow",
    metrics: [
      { name: "Throughput", value: "1,842 veh/h", width: "91%", tone: "cyan" },
      { name: "Queue length", value: "17.6 m", width: "63%", tone: "orange" },
      {
        name: "Stop frequency",
        value: "0.41 / veh",
        width: "59%",
        tone: "cyan",
      },
    ],
  },
  {
    title: "System performance",
    metrics: [
      {
        name: "Capacity utilization",
        value: "68.7%",
        width: "87%",
        tone: "cyan",
      },
      { name: "Control stability", value: "0.93", width: "93%", tone: "cyan" },
    ],
  },
  {
    title: "Fairness / stability",
    metrics: [
      {
        name: "95th percentile delay",
        value: "21.3 s",
        width: "73%",
        tone: "orange",
      },
      { name: "Delay variance", value: "4.8 s²", width: "67%", tone: "cyan" },
    ],
  },
  {
    title: "Physical constraints",
    metrics: [
      {
        name: "Pedestrian exposure",
        value: "2.1 / min",
        width: "52%",
        tone: "orange",
      },
      { name: "Conflict proxy", value: "0.06", width: "25%", tone: "cyan" },
    ],
  },
];

function useReveal() {
  useEffect(() => {
    const items = document.querySelectorAll<HTMLElement>(".reveal");
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.14 },
    );
    items.forEach((item) => {
      observer.observe(item);
    });
    return () => {
      observer.disconnect();
    };
  }, []);
}

function App() {
  const [isLight, setIsLight] = useState(
    () => sessionStorage.getItem("signals-theme") === "light",
  );
  const [liveFlow, setLiveFlow] = useState(1247);
  useReveal();

  useEffect(() => {
    document.title = "UrbanFlow — Signals vs. Roundabouts";
    document.documentElement.classList.toggle("light", isLight);
    document.documentElement.classList.toggle("dark", !isLight);
    sessionStorage.setItem("signals-theme", isLight ? "light" : "dark");
  }, [isLight]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setLiveFlow((current) => {
        const next = current + (Math.random() > 0.5 ? 3 : -2);
        return Math.min(1264, Math.max(1230, next));
      });
    }, 2200);
    return () => {
      window.clearInterval(timer);
    };
  }, []);

  const toggleTheme = () => {
    setIsLight((current) => !current);
  };

  return (
    <main className="site-shell">
      <header className="top-nav">
        <a className="brand" href="#top" data-testid="link-brand">
          <span className="brand-mark" aria-hidden="true" />
          <span className="brand-name">URBANFLOW</span>
        </a>
        <nav className="nav-links" aria-label="Primary navigation">
          <a href="#compare" data-testid="link-compare">
            Compare
          </a>
          <a href="#metrics" data-testid="link-metrics">
            Metrics
          </a>
          <a href="#method" data-testid="link-methodology">
            Method
          </a>
          <button
            className="theme-button"
            type="button"
            onClick={toggleTheme}
            aria-label={
              isLight ? "Switch to dark mode" : "Switch to light mode"
            }
            data-testid="button-theme-toggle"
          >
            {isLight ? <Moon size={15} /> : <Sun size={15} />}
          </button>
        </nav>
      </header>

      <section className="hero" id="top" aria-labelledby="hero-title">
        <div className="hero-grid">
          <div className="hero-copy">
            <div className="hero-kicker eyebrow">
              <span className="signal-dot" /> Intersection control / live model
            </div>
            <h1 id="hero-title" className="display">
              SIGNALS VS.
              <br />
              <em>ROUNDABOUTS.</em>
              <br />
              WHICH ONE WINS?
            </h1>
            <p className="hero-sub">
              A data-driven traffic simulation framework for evaluating
              intersection performance under real-world traffic conditions.
            </p>
            <div className="hero-actions">
              <a
                className="primary-btn"
                href="/app.html"
                data-testid="link-explore-simulation"
              >
                Launch simulation <ArrowDownRight size={15} />
              </a>
              <a
                className="ghost-btn"
                href="#method"
                data-testid="link-read-method"
              >
                Read the method <ArrowRight size={14} />
              </a>
            </div>
            <div className="hero-meta" aria-label="Simulation status">
              <span>
                <strong className="mono" data-testid="text-live-flow">
                  {liveFlow.toLocaleString()}
                </strong>{" "}
                vehicles / hour
              </span>
              <span>
                <strong className="mono">IDM 4.2</strong> physics core
              </span>
              <span>
                <strong className="mono">2 × 10</strong> control metrics
              </span>
            </div>
          </div>
          <div
            className="hero-visual"
            aria-label="Animated isometric intersection visualization"
          >
            <div className="city-canvas">
              <div className="city-base" aria-hidden="true" />
              <div className="road-mark road-h" />
              <div className="road-mark road-v" />
              {buildings.map((building, index) => (
                <div
                  className={`building building-${String(index + 1)}`}
                  key={`${building.x}-${building.y}`}
                  style={
                    {
                      "--w": building.w,
                      "--h": building.h,
                      "--x": building.x,
                      "--y": building.y,
                    } as CSSProperties
                  }
                />
              ))}
              <span
                className="car one"
                style={{ "--car-color": "hsl(188 100% 61%)" } as CSSProperties}
                aria-hidden="true"
              />
              <span
                className="car two"
                style={{ "--car-color": "hsl(22 100% 69%)" } as CSSProperties}
                aria-hidden="true"
              />
              <span
                className="car three"
                style={{ "--car-color": "hsl(260 54% 72%)" } as CSSProperties}
                aria-hidden="true"
              />
              <span
                className="car four"
                style={{ "--car-color": "hsl(188 100% 61%)" } as CSSProperties}
                aria-hidden="true"
              />
              <span
                className="car five"
                style={{ "--car-color": "hsl(22 100% 69%)" } as CSSProperties}
                aria-hidden="true"
              />
              <span
                className="car six"
                style={{ "--car-color": "hsl(188 100% 61%)" } as CSSProperties}
                aria-hidden="true"
              />
              <div className="radar" />
            </div>
          </div>
        </div>
        <div className="scroll-cue">
          <span className="scroll-line" /> Scroll to interrogate the model
        </div>
      </section>

      <section
        className="section-wrap section-space reveal"
        id="compare"
        aria-labelledby="compare-title"
      >
        <div className="section-heading">
          <div>
            <div className="eyebrow">01 / The premise</div>
            <h2 id="compare-title" className="display">
              Two rules.
              <br />
              One junction.
            </h2>
          </div>
          <p>
            Hold demand, geometry, and physics constant. Change only the rule
            that decides who moves next.
          </p>
        </div>
        <div className="compare-grid">
          <article
            className="strategy-card signal"
            data-testid="card-signal-control"
          >
            <div className="strategy-tag">
              <span className="strategy-index">CONTROL 01</span>
              <span>FIXED-TIME</span>
            </div>
            <h3 className="display">
              Signal
              <br />
              control
            </h3>
            <p>
              Phased permission. Predictable cycles. A familiar rhythm that can
              turn demand into a queue.
            </p>
            <div className="mini-intersection signal-mini" aria-hidden="true">
              <span className="mini-road mini-road-h" />
              <span className="mini-road mini-road-v" />
              <span className="mini-building mini-building-a" />
              <span className="mini-building mini-building-b" />
              <span className="mini-building mini-building-c" />
              <span className="mini-signal-light" />
            </div>
          </article>
          <article
            className="strategy-card roundabout"
            data-testid="card-roundabout-control"
          >
            <div className="strategy-tag">
              <span className="strategy-index">CONTROL 02</span>
              <span>MODERN</span>
            </div>
            <h3 className="display">
              Roundabout
              <br />
              control
            </h3>
            <p>
              Yield-based negotiation. Continuous flow. Every entry adapts to
              the movement already in the circle.
            </p>
            <div
              className="mini-intersection roundabout-mini"
              aria-hidden="true"
            >
              <span className="mini-road mini-road-h" />
              <span className="mini-road mini-road-v" />
              <span className="mini-building mini-building-a" />
              <span className="mini-building mini-building-b" />
              <span className="mini-building mini-building-c" />
              <span className="mini-roundabout-ring" />
            </div>
          </article>
        </div>
      </section>

      <section
        className="capabilities section-space reveal"
        aria-labelledby="capabilities-title"
      >
        <div className="section-wrap">
          <div className="section-heading">
            <div>
              <div className="eyebrow">02 / The engine</div>
              <h2 id="capabilities-title" className="display">
                A city that
                <br />
                <em>responds.</em>
              </h2>
            </div>
            <p>
              Not an animation. A calibrated system of vehicles, rules, and
              observations running together.
            </p>
          </div>
          <div className="capability-grid">
            {capabilities.map(({ icon: Icon, title, body }, index) => (
              <article
                className="capability"
                key={title}
                data-testid={`card-capability-${String(index)}`}
              >
                <div className="capability-index mono">0{index + 1}</div>
                <div className="capability-icon">
                  <Icon size={24} strokeWidth={1.5} />
                </div>
                <h3>{title}</h3>
                <p>{body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section
        className="section-wrap section-space metrics-section reveal"
        id="metrics"
        aria-labelledby="metrics-title"
      >
        <div className="metrics-layout">
          <div className="metrics-intro">
            <div className="eyebrow">03 / The evidence</div>
            <h2 id="metrics-title" className="display">
              Ten ways
              <br />
              to measure
              <br />
              <em>better.</em>
            </h2>
            <p>
              Performance is more than speed. We score what the driver feels,
              what the network absorbs, and what the street can safely hold.
            </p>
            <div className="hero-actions" style={{ marginTop: 30 }}>
              <a
                className="ghost-btn"
                href="#winner"
                data-testid="link-see-result"
              >
                See the result <ArrowDownRight size={14} />
              </a>
            </div>
          </div>
          <div className="metric-list">
            {metricGroups.map((group) => (
              <div className="metric-group" key={group.title}>
                <div className="metric-group-title">{group.title}</div>
                {group.metrics.map((metric) => (
                  <div
                    className="metric-row"
                    key={metric.name}
                    data-testid={`metric-row-${metric.name.toLowerCase().replace(/ /g, "-")}`}
                  >
                    <span className="metric-name">{metric.name}</span>
                    <span className="metric-value">{metric.value}</span>
                    <span className="metric-bar" aria-hidden="true">
                      <i
                        className={metric.tone === "orange" ? "orange" : ""}
                        style={{ "--value": metric.width } as CSSProperties}
                      />
                    </span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      </section>

      <section
        className="section-wrap section-space reveal"
        id="winner"
        aria-labelledby="winner-title"
      >
        <div className="score-card">
          <div>
            <div className="eyebrow">04 / Master Efficiency Score</div>
            <h2 id="winner-title" className="display">
              The roundabout
              <br />
              <em>takes the lead.</em>
            </h2>
            <p>
              A weighted composite across throughput, delay, fuel, stability,
              and fairness. The score keeps the trade-offs visible — then makes
              the decision legible.
            </p>
            <div className="score-vs">
              <span>
                SIGNAL CONTROL <b>64.8</b>
              </span>
              <ArrowRight size={13} />
              <span>
                ROUNDABOUT <b>78.6</b>
              </span>
            </div>
          </div>
          <div>
            <div className="score-number" data-testid="text-winning-score">
              78.6
            </div>
            <div className="score-caption mono">
              MASTER EFFICIENCY SCORE / 100
            </div>
          </div>
        </div>
      </section>

      <section
        className="section-wrap section-space reveal"
        id="method"
        aria-labelledby="method-title"
      >
        <div className="methodology">
          <div className="methodology-copy">
            <div className="eyebrow">05 / Under the hood</div>
            <h2 id="method-title" className="display">
              Make the
              <br />
              <em>invisible</em>
              <br />
              count.
            </h2>
            <p>
              Signals vs. Roundabouts turns a familiar planning argument into a
              repeatable experiment. Identical arrival profiles enter the same
              geometry; an Intelligent Driver Model gives each agent a
              human-scale response; the controller is the only variable.
            </p>
            <p>
              Then the twin records every stop, gap, and second — so a design
              decision has a trail back to the street.
            </p>
          </div>
          <div className="tech-stack" aria-label="Technology context">
            <div className="tech-item">
              <strong>
                <Code2 size={18} />
              </strong>
              <span>
                Python simulation core
                <br />
                reproducible scenarios
              </span>
            </div>
            <div className="tech-item">
              <strong>
                <Activity size={18} />
              </strong>
              <span>
                IDM vehicle dynamics
                <br />
                calibrated acceleration
              </span>
            </div>
            <div className="tech-item">
              <strong>
                <Orbit size={18} />
              </strong>
              <span>
                Agent-based flow
                <br />
                lane-level interaction
              </span>
            </div>
            <div className="tech-item">
              <strong>
                <BarChart3 size={18} />
              </strong>
              <span>
                Metric pipeline
                <br />
                decision-ready output
              </span>
            </div>
          </div>
        </div>
      </section>

      <section
        className="section-wrap final-cta reveal"
        aria-labelledby="final-title"
      >
        <div className="eyebrow">06 / Your next junction</div>
        <h2 id="final-title" className="display">
          Stop arguing.
          <br />
          <em>Start observing.</em>
        </h2>
        <p>Put the intersection in motion. Let the evidence choose the rule.</p>
        <a
          className="primary-btn"
          href="/app.html"
          data-testid="link-run-another-scenario"
        >
          Launch simulation <ArrowRight size={15} />
        </a>
      </section>

      <footer className="footer">
        <div className="section-wrap footer-inner">
          <span>URBANFLOW — INTERSECTION CONTROL RESEARCH</span>
          <span>BUILT FOR THE PEOPLE WHO MOVE CITIES</span>
        </div>
      </footer>
    </main>
  );
}

export default App;
