import { FunctionComponent } from "react";
import {
  Check,
  Chips,
  CollapseBox,
  Layout,
  Message,
  Number,
  Section,
  Selector,
  Slider,
  Text,
} from "@/pages/Settings/components";
import { translatorOption } from "./options";

const SettingsProvidersTranslationView: FunctionComponent = () => {
  return (
    <Layout name="Providers">
      <Section header="Translating">
        <Slider
          label="Score for Translated Episode and Movie Subtitles"
          settingKey="settings-translator-default_score"
        ></Slider>
        <Selector
          label="Translator"
          clearable
          options={translatorOption}
          placeholder="Default translator"
          settingKey="settings-translator-translator_type"
        ></Selector>
        <CollapseBox
          settingKey="settings-translator-translator_type"
          on={(val) => val === "gemini"}
        >
          <Text
            label="Gemini model"
            settingKey="settings-translator-gemini_model"
          />
          <Number
            label="Gemini batch size"
            settingKey="settings-translator-gemini_batch_size"
            min={1}
          />
          <Message>
            Number of subtitle lines sent in each Gemini request. Higher values
            reduce the number of API calls and can speed up translation, but may
            increase timeout or response-size errors. Start with 300 (default),
            then lower it if requests fail or raise it gradually if your model
            handles larger batches reliably.
          </Message>
          <Chips
            label="Gemini API keys"
            settingKey="settings-translator-gemini_keys"
            sanitizeFn={(values) => {
              const uniqueKeys = new Set(
                (values ?? []).map((value) => value.trim()).filter(Boolean),
              );
              return Array.from(uniqueKeys);
            }}
          ></Chips>
          <Message>
            You can generate keys here: https://aistudio.google.com/apikey. Add
            as many keys as needed; Bazarr rotates across available keys.
          </Message>
        </CollapseBox>
        <CollapseBox
          settingKey="settings-translator-translator_type"
          on={(val) => val === "openai"}
        >
          <Text
            label="API base URL"
            settingKey="settings-translator-openai_url"
          />
          <Message>
            Any OpenAI-compatible endpoint exposing /chat/completions (e.g.
            https://api.openai.com/v1, https://openrouter.ai/api/v1 or a local
            Ollama/LiteLLM server).
          </Message>
          <Text
            label="API key"
            settingKey="settings-translator-openai_key"
          />
          <Text label="Model" settingKey="settings-translator-openai_model" />
          <Number
            label="Batch size"
            settingKey="settings-translator-openai_batch_size"
            min={1}
          />
          <Message>
            Number of subtitle lines sent in each request. If the model returns
            malformed answers, Bazarr automatically splits the batch in two and
            retries.
          </Message>
        </CollapseBox>
        <CollapseBox
          settingKey="settings-translator-translator_type"
          on={(val) => val === "lingarr"}
        >
          <Text
            label="Lingarr endpoint"
            settingKey="settings-translator-lingarr_url"
          />
          <Message>Base URL of Lingarr (e.g., http://localhost:9876)</Message>
          <Text
            label="Lingarr API Key (optional)"
            settingKey="settings-translator-lingarr_token"
          />
          <Message>
            Optional API key for authentication. Leave empty if your Lingarr
            instance doesn't require authentication.
          </Message>
        </CollapseBox>
        <Check
          label="Add translation info at the beginning"
          settingKey="settings-translator-translator_info"
        ></Check>
        <Check
          label="Tag translated subtitles with .ai (e.g. video.fr.ai.srt)"
          settingKey="settings-translator-mark_ai_translations"
        ></Check>
        <Message>
          Translated files are named video.fr.ai.srt: Bazarr still counts them
          as French, and media servers such as Jellyfin show "ai" in the track
          name.
        </Message>
        <Check
          label="Automatically translate when no subtitles are found"
          settingKey="settings-translator-auto_translate"
        ></Check>
        <CollapseBox
          settingKey="settings-translator-auto_translate"
          on={(val) => val === true}
        >
          <Chips
            label="Languages to generate"
            settingKey="settings-translator-auto_translate_languages"
          ></Chips>
          <Text
            label="Translate from"
            settingKey="settings-translator-auto_translate_source"
          />
          <Number
            label="Wait before translating (hours since the video was added)"
            settingKey="settings-translator-auto_translate_delay_hours"
            min={0}
          />
          <Message>
            Bazarr first searches the providers. If a wanted language is still
            missing after the delay, it is translated from the source language.
            If a real subtitle is published later, the normal upgrade replaces
            or complements the AI one.
          </Message>
        </CollapseBox>
      </Section>
    </Layout>
  );
};

export default SettingsProvidersTranslationView;
