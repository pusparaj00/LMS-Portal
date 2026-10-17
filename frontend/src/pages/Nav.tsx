import { Role } from "../api";

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
      { href: `#/course/${id}/gradebook`, label: "Gradebook" },
    ];
    if (role === "instructor")
      staff.splice(
        2,
        0,
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
      : [{ href: "#/courses", label: "My courses" }];
  return [
    { items: top },
    ...(courseId ? [{ title: "This course", items: course(courseId) }] : []),
  ];
}

export function Nav({ role, courseId, courseTitle, hash }: { role: Role; courseId: number | null; courseTitle?: string; hash: string }) {
  const current = hash || "#/courses";
  return (
    <nav className="side" aria-label="Main">
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
      </div>
    </nav>
  );
}
