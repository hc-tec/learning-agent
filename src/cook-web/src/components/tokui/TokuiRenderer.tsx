'use client';

import React, { useCallback, useLayoutEffect, useRef } from 'react';
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

type TokuiStreamingRendererProps = {
  chunks: string[];
  streamKey: string;
  complete?: boolean;
  theme?: string;
  className?: string;
};

type TokuiStreamingInstance = {
  startStream: (targetContainer?: HTMLElement) => void;
  feed: (chunk: string) => void;
  endStream: () => void;
  disconnect: () => void;
};

const TOKUI_TEXT_PLACEHOLDERS = new Set([
  '请输入答案',
  '请输入你的答案',
  'Enter your answer',
  'Please enter your answer',
]);

const EMPTY_SUBMITTED_RESPONSES: TokuiResponseValue[] = [];

const cssAttributeEscape = (value: string) => value.replace(/["\\]/g, '\\$&');

const tokuiAttrEscape = (value: string) =>
  value.replace(/\\/g, '\\\\').replace(/"/g, '\\"');

const readLegacyTokuiAttr = (attrs: string, name: string) => {
  const pattern = new RegExp(
    `${name}\\s*=\\s*(?:"([^"]*)"|'([^']*)'|([^\\s\\]]+))`,
    'i',
  );
  const match = attrs.match(pattern);
  return match?.[1] ?? match?.[2] ?? match?.[3] ?? '';
};

const normalizeLegacyTokuiInputTag = (match: string, attrs: string) => {
  if (!/\b(field_id|field_type|label|required)\s*=/i.test(attrs)) {
    return match;
  }

  const fieldId = readLegacyTokuiAttr(attrs, 'field_id');
  if (!fieldId) {
    return match;
  }

  const fieldType = readLegacyTokuiAttr(attrs, 'field_type') || 'text';
  const label = readLegacyTokuiAttr(attrs, 'label');
  const required = /(?:\brequired\s*=\s*(?:"true"|'true'|true|1)|\brequired\b)/i.test(
    attrs,
  );
  const tokuiType = fieldType === 'number' ? 'number' : 'text';
  const parts = [
    `n:"${tokuiAttrEscape(fieldId)}"`,
    `t:${tokuiType}`,
  ];
  if (label) {
    parts.push(`l:"${tokuiAttrEscape(label)}"`);
  }
  if (required) {
    parts.push('req');
  }
  return `[input ${parts.join(' ')}]`;
};

const normalizeLegacyTokuiMediaTag = (attrs: string) => {
  const mediaType = (readLegacyTokuiAttr(attrs, 'type') || 'image').toLowerCase();
  const url = readLegacyTokuiAttr(attrs, 'url') || readLegacyTokuiAttr(attrs, 'src');
  const title = readLegacyTokuiAttr(attrs, 'title') || '教学素材';
  if (!url) {
    return `[p v:muted 素材待提供：${tokuiAttrEscape(title)}]`;
  }
  if (mediaType === 'video') {
    return `[video s:"${tokuiAttrEscape(url)}"]`;
  }
  return `[img s:"${tokuiAttrEscape(url)}" tt:"${tokuiAttrEscape(title)}" alt:"${tokuiAttrEscape(title)}"]`;
};

export const normalizeLearnerTokuiDsl = (dsl: string) =>
  dsl
    .replace(
      /\[input\b([^\]]*)\]/gi,
      (match, attrs) => normalizeLegacyTokuiInputTag(match, attrs),
    )
    .replace(
      /\[submit\b([^\]]*)\/?\]/gi,
      (_match, attrs) => {
        const label = readLegacyTokuiAttr(attrs, 'label') || '提交';
        return `[btn tx:"${tokuiAttrEscape(label)}" v:primary act:submit]`;
      },
    )
    .replace(
      /\[media\b([^\]]*)\/?\]/gi,
      (_match, attrs) => normalizeLegacyTokuiMediaTag(attrs),
    );

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
    const displayValue = valueToDisplayString(value);
    if (elements[0] instanceof HTMLTextAreaElement) {
      elements[0].defaultValue = displayValue;
      elements[0].textContent = displayValue;
    }
    elements[0].value = displayValue;
  });
};

const ensureInteractionFieldNames = (
  root: HTMLDivElement,
  interactionSchema: TokuiInteractionField[],
) => {
  const fields = interactionSchema.filter(field => field.field_id);
  if (!fields.length) return;
  const unnamedElements = Array.from(
    root.querySelectorAll<
      HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
    >('input, textarea, select'),
  ).filter(element => !element.name && !element.id);

  if (
    unnamedElements.length !== fields.length &&
    !(unnamedElements.length === 1 && fields.length === 1)
  ) {
    return;
  }

  unnamedElements.forEach((element, index) => {
    const field = fields[index] || fields[0];
    if (!field?.field_id) return;
    element.name = field.field_id;
  });
};

const setReadOnlyState = (root: HTMLDivElement, readOnly: boolean) => {
  root
    .querySelectorAll<HTMLInputElement | HTMLTextAreaElement>('input, textarea')
    .forEach(element => {
      element.readOnly = readOnly;
    });
  root
    .querySelectorAll<HTMLSelectElement | HTMLButtonElement>('select, button')
    .forEach(element => {
      element.disabled = readOnly;
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
  const latestRenderStateRef = useRef({
    interactionSchema,
    readOnly,
    submittedResponses,
  });
  latestRenderStateRef.current = {
    interactionSchema,
    readOnly,
    submittedResponses,
  };

  useLayoutEffect(() => {
    const root = rootRef.current;
    if (!root || !dsl) return;
    const latestRenderState = latestRenderStateRef.current;

    root.replaceChildren();
    const ui = new TokUI({ container: root, theme });
    if (theme) {
      try {
        setTheme(theme);
      } catch {
        // Keep rendering even if an optional theme cannot be applied.
      }
    }
    ui.render(normalizeLearnerTokuiDsl(dsl));
    ensureInteractionFieldNames(root, latestRenderState.interactionSchema);
    normalizeRenderedFields(root);
    applySubmittedResponses(root, latestRenderState.submittedResponses);
    setReadOnlyState(root, latestRenderState.readOnly);

    return () => {
      try {
        ui.disconnect();
      } catch {
        // TokUI cleanup is best-effort; the wrapper owns the DOM reset.
      }
      root.replaceChildren();
    };
  }, [dsl, theme]);

  useLayoutEffect(() => {
    const root = rootRef.current;
    if (!root || !dsl) return;
    ensureInteractionFieldNames(root, interactionSchema);
    applySubmittedResponses(root, submittedResponses);
    setReadOnlyState(root, readOnly);
  }, [dsl, interactionSchema, readOnly, submittedResponses]);

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
        const isSubmitAction = trigger?.matches('[data-tokui-act="submit"]');
        const isFormButton = Boolean(trigger?.closest('form'));
        const isLikelySubmitButton =
          Boolean(interactionSchema.length) &&
          /提交|submit/i.test(trigger?.textContent || '');
        if (
          trigger &&
          rootRef.current?.contains(trigger) &&
          (isSubmitAction || isFormButton || isLikelySubmitButton) &&
          !(trigger instanceof HTMLButtonElement && trigger.type === 'submit')
        ) {
          submitResponses();
        }
      }}
    >
    </div>
  );
}

export function TokuiStreamingRenderer({
  chunks,
  streamKey,
  complete = false,
  theme = 'default',
  className,
}: TokuiStreamingRendererProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const uiRef = useRef<TokuiStreamingInstance | null>(null);
  const fedChunkCountRef = useRef(0);
  const completedRef = useRef(false);

  useLayoutEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    root.replaceChildren();
    const ui = new TokUI({ container: root, theme }) as TokuiStreamingInstance;
    if (theme) {
      try {
        setTheme(theme);
      } catch {
        // Keep streaming even if an optional theme cannot be applied.
      }
    }
    ui.startStream(root);
    uiRef.current = ui;
    fedChunkCountRef.current = 0;
    completedRef.current = false;

    return () => {
      try {
        ui.disconnect();
      } catch {
        // TokUI cleanup is best-effort; the wrapper owns the DOM reset.
      }
      uiRef.current = null;
      root.replaceChildren();
    };
  }, [streamKey, theme]);

  useLayoutEffect(() => {
    const ui = uiRef.current;
    if (!ui) return;
    const nextChunks = chunks.slice(fedChunkCountRef.current);
    nextChunks.forEach(chunk => {
      if (chunk) {
        ui.feed(chunk);
      }
    });
    fedChunkCountRef.current = chunks.length;
    if (complete && !completedRef.current) {
      ui.endStream();
      completedRef.current = true;
    }
  }, [chunks, complete]);

  return (
    <div
      ref={rootRef}
      data-testid='tokui-streaming-renderer-root'
      className={className}
    />
  );
}
