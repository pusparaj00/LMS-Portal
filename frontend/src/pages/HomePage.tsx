import { FormEvent, ReactNode, useEffect, useState } from "react";

import { ThemeToggle } from "../design/ThemeToggle";
import { CONCEPTS, FAQ, HERO_NAMES, ROWS, STAGES, STATUS } from "./home/homeData";
import { LiveQuestion } from "./home/LiveQuestion";
import "./home/home.css";

export const PREFILL_KEY = "lms-prefill-email";

const ANCHORS = [
  { id: "question", label: "Try a question" },
  { id: "how", label: "How it works" },
  { id: "features", label: "What you get" },
  { id: "status", label: "Status" },
  { id: "faq", label: "FAQ" },
];

function reducedMotion(): boolean {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}

function scrollToSection(id: string) {
  document.querySelector("details.pubmenu")?.removeAttribute("open");
  const section = document.getElementById(id);
  if (!section) return;
  section.scrollIntoView({ behavior: reducedMotion() ? "auto" : "smooth" });
  section.querySelector<HTMLElement>("h2")?.focus({ preventScroll: true });
}

/** Anchor links on the public page cannot use plain "#id" hrefs, because the app routes on the hash. */
function SectionLink({ id, children }: { id: string; children: ReactNode }) {
  return (
    <a
      href={`#/${id}`}
      onClick={(e) => {
        e.preventDefault();
        scrollToSection(id);
      }}
    >
      {children}
    </a>
  );
}

/** Top bar of the public layout: the name, a few links and one action. Its ink follows the chapter beneath it. */
export function PublicBar({ dashboardHref, onHome = false }: { dashboardHref?: string; onHome?: boolean }) {
  const [tone, setTone] = useState("paper");
  useEffect(() => {
    if (!onHome) return;
    let frame = 0;
    const update = () => {
      frame = 0;
      const chapter = Array.from(document.querySelectorAll<HTMLElement>("[data-tone]")).find((el) => {
        const r = el.getBoundingClientRect();
        return r.top <= 36 && r.bottom > 36;
      });
      if (chapter?.dataset.tone) setTone(chapter.dataset.tone);
    };
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };
    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      if (frame) cancelAnimationFrame(frame);
    };
  }, [onHome]);

  return (
    <header className={`pubbar ${onHome ? "pubbar-fixed" : ""}`} data-tone-bar={onHome ? tone : "paper"}>
      <a
        className="skip"
        href="#/"
        onClick={(e) => {
          e.preventDefault();
          document.getElementById("content")?.focus();
        }}
      >
        Skip to content
      </a>
      <a className="pubbrand" href={dashboardHref ? "#/home" : "#/"}>
        Adaptive LMS
      </a>
      {onHome && (
        <nav className="pubnav" aria-label="Sections">
          {ANCHORS.map((a) => (
            <SectionLink key={a.id} id={a.id}>
              {a.label}
            </SectionLink>
          ))}
        </nav>
      )}
      <div className="pubactions">
        {dashboardHref ? (
          <a className="button primary" href={dashboardHref}>
            Open dashboard
          </a>
        ) : (
          <>
            <a className="pubtext" href="#/login">
              Log in
            </a>
            <a className="button primary" href="#/register">
              Create account
            </a>
          </>
        )}
      </div>
      {onHome && (
        <details className="pubmenu">
          <summary>Menu</summary>
          <div>
            {ANCHORS.map((a) => (
              <SectionLink key={a.id} id={a.id}>
                {a.label}
              </SectionLink>
            ))}
          </div>
        </details>
      )}
    </header>
  );
}

/** Adds `in` to every `[data-rise]` element as it scrolls into view. Without script the content simply shows. */
function useReveal() {
  useEffect(() => {
    const items = Array.from(document.querySelectorAll<HTMLElement>("[data-rise]"));
    if (reducedMotion() || !("IntersectionObserver" in window)) {
      items.forEach((el) => el.classList.add("in"));
      return;
    }
    document.documentElement.classList.add("js-rise");
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.classList.add("in");
            observer.unobserve(entry.target);
          }
        }
      },
      { threshold: 0.15, rootMargin: "0px 0px -8% 0px" },
    );
    items.forEach((el) => observer.observe(el));
    return () => {
      observer.disconnect();
      document.documentElement.classList.remove("js-rise");
    };
  }, []);
}

/** Steps through `length` items once, then stops (moving text must not run for ever). `paused` stops it sooner. */
function useCycle(length: number, ms: number, paused: boolean): number {
  const [index, setIndex] = useState(0);
  useEffect(() => {
    if (reducedMotion() || paused) return;
    const timer = window.setInterval(
      () =>
        setIndex((i) => {
          if (i + 1 >= length) window.clearInterval(timer);
          return Math.min(i + 1, length - 1);
        }),
      ms,
    );
    return () => window.clearInterval(timer);
  }, [length, ms, paused]);
  return index;
}

function Headline({ name }: { name: string }) {
  return (
    <div className="hero2-head" aria-hidden="true">
      <span className="hero2-line">Every error</span>
      <span className="hero2-line">
        has a{" "}
        <span className="frame">
          <span key={name} className="frame-text">
            {name}
          </span>
        </span>
      </span>
    </div>
  );
}

function Hero({ dashboardHref, still, onStill }: { dashboardHref?: string; still: boolean; onStill: () => void }) {
  const name = HERO_NAMES[useCycle(HERO_NAMES.length, 2600, still)];
  return (
    <section className="chapter hero2" data-tone="hero" aria-labelledby="hero-h">
      <h1 id="hero-h" className="sr-only">
        Every error has a name.
      </h1>
      <div className="hero2-field hero2-top" />
      <div className="hero2-field hero2-bottom" />
      <Headline name={name} />
      <p className="hero2-sub">
        Practise Python, Java or C in a sandbox. Each wrong answer is traced to a misconception, explained with an answer that is
        checked first, and tracked as mastery you can audit.
        {!dashboardHref && (
          <>
            {" "}
            <SectionLink id="question">Try one question.</SectionLink>
          </>
        )}
      </p>
      <button type="button" className="hero2-still" aria-pressed={still} onClick={onStill}>
        {still ? "Play the moving words" : "Pause the moving words"}
      </button>
    </section>
  );
}

function Question() {
  return (
    <section id="question" className="chapter" data-tone="paper" aria-labelledby="question-h">
      <div className="wrap">
        <h2 id="question-h" tabIndex={-1} className="display rise" data-rise>
          Try one question.
        </h2>
        <p className="lede rise" data-rise>
          These are real items from the course bank. A wrong answer maps to the misconception it came from.
        </p>
        <div className="rise" data-rise>
          <LiveQuestion />
        </div>
      </div>
    </section>
  );
}

function How() {
  return (
    <section id="how" className="chapter" data-tone="surface" aria-labelledby="how-h">
      <div className="wrap">
        <h2 id="how-h" tabIndex={-1} className="display rise" data-rise>
          Checked before you see it.
        </h2>
        <ol className="stages" aria-label="What happens when a submission fails">
          {STAGES.map((s, i) => (
            <li key={s.name} className={`stage stage-${i} rise`} style={{ flexGrow: Math.max(s.grow, 7) }} data-rise>
              <div className="stage-bar">
                <span className="stage-name">{s.name}</span>
                <span className="stage-time">{s.time}</span>
              </div>
              <p>{s.text}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

function Moth() {
  return (
    <section className="chapter moth" data-tone="ink" aria-labelledby="moth-h">
      <div className="moth-text">
        <h2 id="moth-h" tabIndex={-1} className="statement rise" data-rise>
          Mistakes have always needed names.
        </h2>
        <p className="rise" data-rise>
          In 1947 a moth was taped into a computer's logbook beside the words “First actual case of bug being found.”
        </p>
      </div>
      <div className="moth-picture rise" data-rise>
        <img
          src="/archive/first-bug.jpg"
          width={1920}
          height={1519}
          loading="lazy"
          alt="A page of a 1947 computer logbook with a moth taped to it and the handwritten words: First actual case of bug being found"
        />
      </div>
    </section>
  );
}

function Features() {
  return (
    <section id="features" className="chapter" data-tone="paper" aria-labelledby="features-h">
      <div className="axis">
        <h2 id="features-h" tabIndex={-1} className="display rise" data-rise>
          What you get here.
        </h2>
        {ROWS.map((row) => (
          <article key={row.title} className="row">
            <div className="row-text rise" data-rise>
              <h3>{row.title}</h3>
              <p>{row.text}</p>
            </div>
            <img
              className="row-picture rise"
              data-rise
              src={row.image}
              alt={row.alt}
              loading="lazy"
              style={{ width: row.width, aspectRatio: row.ratio }}
            />
          </article>
        ))}
      </div>
    </section>
  );
}

function Proof({ still }: { still: boolean }) {
  const lit = useCycle(CONCEPTS.length, 2000, still);
  return (
    <section className="chapter" data-tone="surface" aria-labelledby="proof-h">
      <div className="wrap">
        <h2 id="proof-h" tabIndex={-1} className="proof-head rise" data-rise>
          Twelve concepts, each tracked.
        </h2>
        <ul className="proof-list rise" data-rise>
          {CONCEPTS.map((c, i) => (
            <li key={c} className={i === lit ? "proof-name is-lit" : "proof-name"}>
              {c}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function Status() {
  return (
    <section id="status" className="chapter" data-tone="paper" aria-labelledby="status-h">
      <div className="wrap status-grid">
        <h2 id="status-h" tabIndex={-1} className="head rise" data-rise>
          Working today, and not yet.
        </h2>
        <div className="status-side">
          <p className="status-name">Status</p>
          <table className="status-table rise" data-rise>
            <tbody>
              {STATUS.map((r) => (
                <tr key={r.what}>
                  <th scope="row">{r.who}</th>
                  <td>{r.what}</td>
                  <td className={r.status === "Live" ? "is-live" : ""}>{r.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted small">
            A prototype built for a course review. Accuracy figures come from simulated students; nothing here is a claim
            about learning outcomes.
          </p>
        </div>
      </div>
    </section>
  );
}

function Faq() {
  return (
    <section id="faq" className="chapter" data-tone="paper" aria-labelledby="faq-h">
      <div className="wrap">
        <h2 id="faq-h" tabIndex={-1} className="head rise" data-rise>
          Questions people ask.
        </h2>
        <div className="faq-list">
          {FAQ.map(([q, a]) => (
            <details key={q} className="faq2 rise" data-rise>
              <summary>{q}</summary>
              <p>{a}</p>
            </details>
          ))}
        </div>
      </div>
    </section>
  );
}

function Begin() {
  const [email, setEmail] = useState("");
  function go(event: FormEvent) {
    event.preventDefault();
    try {
      sessionStorage.setItem(PREFILL_KEY, email.trim());
    } catch {
      // the next page then simply starts empty
    }
    window.location.hash = "#/register";
  }
  return (
    <section className="chapter begin" data-tone="accent" aria-label="Create an account">
      <form className="begin-sentence rise" data-rise onSubmit={go}>
        <label htmlFor="begin-email">Find where you stand,</label>{" "}
        <input id="begin-email" type="email" required autoComplete="email" placeholder="you@school.edu" value={email} onChange={(e) => setEmail(e.target.value)} />{" "}
        <button type="submit">begin</button>
      </form>
      <p className="begin-note rise" data-rise>
        You choose a password on the next page. Your instructor gives you a class code to join a course.
      </p>
    </section>
  );
}

const CREDITS: [string, string, string][] = [
  ["First Computer Bug, 1947", "Naval Surface Warfare Center, Dahlgren", "https://commons.wikimedia.org/wiki/File:First_Computer_Bug,_1947.jpg"],
  ["Diagram for the computation of Bernoulli numbers", "Ada Lovelace", "https://commons.wikimedia.org/wiki/File:Diagram_for_the_computation_of_Bernoulli_numbers.jpg"],
  ["Portrait of Ada King, Countess of Lovelace", "Alfred Edward Chalon", "https://commons.wikimedia.org/wiki/File:Ada_Lovelace_portrait.jpg"],
  ["Two women operating ENIAC", "U.S. Army", "https://commons.wikimedia.org/wiki/File:Two_women_operating_ENIAC_(full_resolution).jpg"],
  ["Hollerith Punched Card", "1895", "https://commons.wikimedia.org/wiki/File:Hollerith_Punched_Card.jpg"],
];

function Footer({ dashboardHref }: { dashboardHref?: string }) {
  return (
    <footer className="chapter foot" data-tone="ink">
      <div className="foot-top">
        <div>
          <p className="foot-invite">Start with one question.</p>
          {!dashboardHref && (
            <a className="button primary" href="#/register">
              Create account
            </a>
          )}
        </div>
        <ul className="foot-links">
          <li>
            <a href="#/login">Log in</a>
          </li>
          <li>
            <SectionLink id="status">Status</SectionLink>
          </li>
          <li>
            <SectionLink id="faq">FAQ</SectionLink>
          </li>
          <li>
            <ThemeToggle />
          </li>
        </ul>
      </div>
      <p className="foot-credits">
        Pictures, all public domain, from Wikimedia Commons:{" "}
        {CREDITS.map(([title, by, href], i) => (
          <span key={href}>
            <a href={href}>{title}</a> ({by}){i < CREDITS.length - 1 ? "; " : "."}
          </span>
        ))}{" "}
        A prototype built for a course review.
      </p>
      <div className="foot-name" aria-hidden="true">
        Adaptive LMS
      </div>
    </footer>
  );
}

export function HomePage({ dashboardHref }: { dashboardHref?: string }) {
  useReveal();
  const [still, setStill] = useState(false);
  return (
    <div className={still ? "home is-still" : "home"}>
      <PublicBar dashboardHref={dashboardHref} onHome />
      <main id="content" tabIndex={-1}>
        <Hero dashboardHref={dashboardHref} still={still} onStill={() => setStill(!still)} />
        <Question />
        <How />
        <Moth />
        <Features />
        <Proof still={still} />
        <Status />
        <Faq />
        {!dashboardHref && <Begin />}
      </main>
      <Footer dashboardHref={dashboardHref} />
    </div>
  );
}
