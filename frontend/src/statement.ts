/** Statements keep markdown fences around code for the model; people read the code without them. */
export function withoutFences(statement: string): string {
  return statement
    .split("\n")
    .filter((line) => !/^```\w*$/.test(line.trim()))
    .join("\n")
    .trim();
}
