import { expect, test as setup } from "@playwright/test";
import { clearMail, messages, signInLink } from "./mail";
import { ALLOWED } from "./seed";

// M7-01 "allowlist login": a signed-out visit goes to /login; another address gets the same answer and no email; the
// allowed address gets a magic link that signs in. The session is saved for the other tests.
setup("allowlist login", async ({ page, request }) => {
  await clearMail(request);
  await page.goto("/candidates");
  await expect(page).toHaveURL(/\/login$/);

  await page.getByLabel("Email").fill("intruder@example.com");
  await page.getByRole("button", { name: "Send sign-in link" }).click();
  await expect(page.getByRole("status")).toContainText("If that address is allowed");

  await page.getByLabel("Email").fill(ALLOWED);
  await page.getByRole("button", { name: "Send sign-in link" }).click();
  await expect(page.getByRole("status")).toContainText("If that address is allowed");
  const link = await signInLink(request, ALLOWED);
  expect(await messages(request, "intruder@example.com")).toEqual([]);

  await page.goto(link);
  const landed = page.getByRole("heading", { level: 1, name: "This week" });
  if (!(await landed.isVisible())) await page.waitForLoadState("networkidle");
  const where = `landed on ${page.url()}: ${(await page.locator("body").innerText()).slice(0, 400)}`;
  await expect(landed, where).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
  await page.context().storageState({ path: "e2e/.auth/user.json" });
});
