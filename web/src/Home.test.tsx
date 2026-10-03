import { personName } from "./Home";

test("the person is named by their name, else their address", () => {
  expect(personName({ name: "Dana Whitfield", email: "dana@example.com" })).toBe("Dana Whitfield");
  expect(personName({ email: "dana@example.com" })).toBe("dana@example.com");
  expect(personName(undefined)).toBe("");
});
