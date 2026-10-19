import { useEffect, useState } from "react";

import { Role } from "../api";
import { RECENT_EVENT, getRecent } from "../design/recent";

type Item = { href: string; label: string; prefix?: string };

/** TR-P-09, F-01: one menu per role, so each role reaches its main tasks in one click. */
function sections(role: Role, courseId: number | null): { title?: string; items: Item[] }[] {
  const course = (id: number): Item[] => {
    if (role === "student")
      return [
        { href: `#/course/${id}`, label: "Course home" },
        { href: `#/placement/${id}`, label: "Placement test" },
        { href: `#/mastery/${id}`, label: "My progress", prefix: `#/mastery/${id}/` },
      ];
    const staff: Item[] = [
      { href: `#/course/${id}`, label: "Problems", prefix: `#/course/${id}/problem/` },
      { href: `#/class/${id}`, label: "Class overview", prefix: `#/class/${id}/` },
      { href: `#/course/${id}/analytics`, label: "Analytics" },
      { href: `#/course/${id}/gradebook`, label: "Gradebook" },
    ];
    if (role === "instructor")
      staff.splice(
        3,
        0,
        { href: `#/course/${id}/content`, label: "Content" },
        { href: `#/course/${id}/quizzes`, label: "Quizzes" },
        { href: `#/course/${id}/assignments`, label: "Assignments" },
        { href: `#/course/${id}/notes`, label: "Course notes" },
      );
    return staff;
  };
  const top: Item[] =
    role === "admin"
      ? [
          { href: "#/admin", label: "Users" },
          { href: "#/courses", label: "All courses" },
        ]
      : [
          { href: "#/dashboard", label: "Dashboard" },
          { href: "#/courses", label: "My courses" },
          ...(role === "student" ? [{ href: "#/grades", label: "Grades" }] : []),
        ];
  return [
    { items: top },
    ...(courseId ? [{ title: "This course", items: course(courseId) }] : []),
  ];
}

export function Nav({ role, courseId, courseTitle, hash }: { role: Role; courseId: number | null; courseTitle?: string; hash: string }) {
  const current = hash || "#/courses";
  const [recent, setRecent] = useState(getRecent);
  useEffect(() => {
    const refresh = () => setRecent(getRecent());
    window.addEventListener(RECENT_EVENT, refresh);
    return () => window.removeEventListener(RECENT_EVENT, refresh);
  }, []);
  return (
    <nav className="side" id="main-menu" aria-label="Main">
      <div className="side-inner">
        {sections(role, courseId).map((section, i) => (
          <div key={i} className="side-section">
            {section.title && (
              <p className="side-title">{section.title === "This course" && courseTitle ? courseTitle : section.title}</p>
            )}
            <ul>
              {section.items.map((item) => {
                const active = current === item.href || (item.prefix !== undefined && current.startsWith(item.prefix));
                return (
                  <li key={item.href}>
                    <a href={item.href} aria-current={active ? "page" : undefined}>
                      {item.label}
                    </a>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
        {role === "student" && recent.length > 0 && (
          <div className="side-section">
            <p className="side-title side-label">//recent</p>
            <ul>
              {recent.map((r) => (
                <li key={r.href}>
                  <a href={r.href} aria-current={current === r.href ? "page" : undefined}>
                    {r.title}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </nav>
  );
}
