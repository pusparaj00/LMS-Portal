// The course's language, mapped to the language id the monaco editor uses to highlight it.
export function editorLanguage(language: string | undefined | null): string {
  switch (language) {
    case "java":
      return "java";
    case "c":
      return "cpp";
    default:
      return "python";
  }
}

// A short starter comment shown in an empty editor, in the language the course teaches.
export function starterComment(language: string | undefined | null): string {
  switch (language) {
    case "java":
      return "// Read from the scanner, print the answer.\n";
    case "c":
      return "// Read with scanf, print the answer.\n";
    default:
      return "# Read from input(), print the answer.\n";
  }
}

// The human-facing name of a language, for badges.
export function languageName(language: string | undefined | null): string {
  switch (language) {
    case "java":
      return "Java";
    case "c":
      return "C";
    default:
      return "Python";
  }
}
