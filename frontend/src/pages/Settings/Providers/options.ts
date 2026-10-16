import { SelectorOption } from "@/components";

export const translatorOption: SelectorOption<string>[] = [
  {
    label: "Google Translate",
    value: "google_translate",
  },
  {
    label: "Gemini",
    value: "gemini",
  },
  {
    label: "OpenAI-compatible (LLM)",
    value: "openai",
  },
  {
    label: "Lingarr",
    value: "lingarr",
  },
];

export const antiCaptchaOption: SelectorOption<string>[] = [
  {
    label: "Anti-Captcha",
    value: "anti-captcha",
  },
  {
    label: "Death by Captcha",
    value: "death-by-captcha",
  },
  {
    label: "CaptchaAI",
    value: "captchaai",
  },
];
