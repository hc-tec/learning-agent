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
  readOnly?: boolean;
  submittedResponses?: TokuiResponseValue[];
  onSubmitResponses?: (responses: TokuiResponseValue[]) => void;
};

const TOKUI_TEXT_PLACEHOLDERS = new Set([
  '请输入答案',
  '请输入你的答案',
  'Enter your answer',
  'Please enter your answer',
]);

const EMPTY_SUBMITTED_RESPONSES: TokuiResponseValue[] = [];

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

const findFieldElements = (
  root: HTMLDivElement,
  fieldId: string,
): Array<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement> => {
  if (!fieldId) return [];
  const selector = `[name="${cssAttributeEscape(fieldId)}"]`;
  const elements = Array.from(
    root.querySelectorAll<
      HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
    >(selector),
  );
  const idElement = root.ownerDocument.getElementById(fieldId);
  if (
    isFormField(idElement) &&
    root.contains(idElement) &&
    !elements.includes(idElement)
  ) {
    elements.push(idElement);
  }
  return elements;
};

const valueToDisplayString = (value: unknown) => {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  return JSON.stringify(value);
};

const applySubmittedResponses = (
  root: HTMLDivElement,
  responses: TokuiResponseValue[] = [],
) => {
  responses.forEach(response => {
    const elements = findFieldElements(root, response.field_id);
    if (!elements.length) return;
    const value = response.value;
    if (elements[0] instanceof HTMLInputElement && elements[0].type === 'checkbox') {
      const values = Array.isArray(value) ? value.map(String) : [];
      elements.forEach(element => {
        if (element instanceof HTMLInputElement) {
          element.checked =
            typeof value === 'boolean'
              ? value
              : values.includes(element.value || 'true');
        }
      });
      return;
    }
    if (elements[0] instanceof HTMLInputElement && elements[0].type === 'radio') {
      elements.forEach(element => {
        if (element instanceof HTMLInputElement) {
          element.checked = element.value === valueToDisplayString(value);
        }
      });
      return;
    }
    elements[0].value = valueToDisplayString(value);
  });
};

const makeReadOnly = (root: HTMLDivElement) => {
  root
    .querySelectorAll<HTMLInputElement | HTMLTextAreaElement>('input, textarea')
    .forEach(element => {
      element.readOnly = true;
    });
  root
    .querySelectorAll<HTMLSelectElement | HTMLButtonElement>('select, button')
    .forEach(element => {
      element.disabled = true;
    });
};

const readFieldValue = (root: HTMLDivElement, field: TokuiInteractionField) => {
  const elements = findFieldElements(root, field.field_id);
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
  readOnly = false,
  submittedResponses = EMPTY_SUBMITTED_RESPONSES,
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
    applySubmittedResponses(root, submittedResponses);
    if (readOnly) {
      makeReadOnly(root);
    }

    return () => {
      try {
        ui.disconnect();
      } catch {
        // TokUI cleanup is best-effort; the wrapper owns the DOM reset.
      }
      root.replaceChildren();
    };
  }, [dsl, readOnly, submittedResponses, theme]);

  const submitResponses = useCallback(() => {
    if (readOnly || !rootRef.current || !onSubmitResponses) return;
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
  }, [interactionSchema, onSubmitResponses, readOnly]);

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
