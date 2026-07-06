'use client';

import React, { useCallback, useEffect, useRef } from 'react';
import { TokUI, setTheme } from '@jboltai/tokui';
import '@jboltai/tokui/css';

export type TokuiInteractionField = {
  field_id: string;
  field_type?: string;
  label?: string;
  required?: boolean;
  blocking?: boolean;
  continue_on_submit?: boolean;
  continuation_hint?: string;
};

export type TokuiResponseValue = {
  field_id: string;
  field_type: string;
  value: unknown;
};

type TokuiRendererProps = {
  dsl?: string;
  interactionSchema?: TokuiInteractionField[];
  theme?: string;
  className?: string;
  onSubmitResponses?: (responses: TokuiResponseValue[]) => void;
};

const TOKUI_TEXT_PLACEHOLDERS = new Set([
  '请输入答案',
  '请输入你的答案',
  'Enter your answer',
  'Please enter your answer',
]);

const cssAttributeEscape = (value: string) => value.replace(/["\\]/g, '\\$&');

const isFormField = (
  element: Element | null,
): element is HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement =>
  element instanceof HTMLInputElement ||
  element instanceof HTMLTextAreaElement ||
  element instanceof HTMLSelectElement;

const normalizeRenderedFields = (root: HTMLDivElement) => {
  root.querySelectorAll<HTMLTextAreaElement>('textarea').forEach(textarea => {
    const value = textarea.value.trim();
    if (!textarea.placeholder && TOKUI_TEXT_PLACEHOLDERS.has(value)) {
      textarea.placeholder = value;
      textarea.value = '';
      textarea.defaultValue = '';
      textarea.textContent = '';
    }
  });
};

const readFieldValue = (root: HTMLDivElement, field: TokuiInteractionField) => {
  const selector = `[name="${cssAttributeEscape(field.field_id)}"]`;
  const elements = Array.from(
    root.querySelectorAll<
      HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
    >(selector),
  );
  const idElement = root.ownerDocument.getElementById(field.field_id);
  if (
    isFormField(idElement) &&
    root.contains(idElement) &&
    !elements.includes(idElement)
  ) {
    elements.push(idElement);
  }
  if (!elements.length) return undefined;
  if (
    elements[0] instanceof HTMLInputElement &&
    elements[0].type === 'checkbox'
  ) {
    const checked = elements
      .filter(element => element instanceof HTMLInputElement && element.checked)
      .map(element => element.value || true);
    return elements.length === 1 ? Boolean(elements[0].checked) : checked;
  }
  if (elements[0] instanceof HTMLInputElement && elements[0].type === 'radio') {
    const checked = elements.find(
      element => element instanceof HTMLInputElement && element.checked,
    );
    return checked?.value;
  }
  return elements[0].value;
};

export default function TokuiRenderer({
  dsl,
  interactionSchema = [],
  theme = 'default',
  className,
  onSubmitResponses,
}: TokuiRendererProps) {
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const root = rootRef.current;
    if (!root || !dsl) return;

    root.replaceChildren();
    const ui = new TokUI({ container: root, theme });
    if (theme) {
      try {
        setTheme(theme);
      } catch {
        // Keep rendering even if an optional theme cannot be applied.
      }
    }
    ui.render(dsl);
    normalizeRenderedFields(root);

    return () => {
      try {
        ui.disconnect();
      } catch {
        // TokUI cleanup is best-effort; the wrapper owns the DOM reset.
      }
      root.replaceChildren();
    };
  }, [dsl, theme]);

  const submitResponses = useCallback(() => {
    if (!rootRef.current || !onSubmitResponses) return;
    const responses = interactionSchema
      .map(field => ({
        field_id: field.field_id,
        field_type: field.field_type || 'text',
        value: readFieldValue(rootRef.current as HTMLDivElement, field),
      }))
      .filter(response => response.value !== undefined);
    if (responses.length) {
      onSubmitResponses(responses);
    }
  }, [interactionSchema, onSubmitResponses]);

  if (!dsl) {
    return null;
  }

  return (
    <div
      ref={rootRef}
      data-testid='tokui-renderer-root'
      className={className}
      onSubmit={event => {
        event.preventDefault();
        submitResponses();
      }}
      onClick={event => {
        const target = event.target as HTMLElement | null;
        const trigger = target?.closest<HTMLElement>(
          '[data-tokui-act="submit"], button[data-tokui-tag="btn"].tokui-btn',
        );
        if (
          trigger &&
          rootRef.current?.contains(trigger) &&
          trigger.closest('form') &&
          !(trigger instanceof HTMLButtonElement && trigger.type === 'submit')
        ) {
          submitResponses();
        }
      }}
    >
    </div>
  );
}
