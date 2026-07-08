'use client';

import React, { useCallback, useLayoutEffect, useRef } from 'react';
import { TokUI, setTheme } from '@jboltai/tokui';
import '@jboltai/tokui/css';

export type TokuiInteractionField = {
  field_id: string;
  field_type?: string;
  label?: string;
  options?: Array<{ value: string; label: string }>;
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

const FIELD_TYPE_ALIASES: Record<string, string> = {
  text: 'short_text',
  textarea: 'short_text',
  short: 'short_text',
  short_text: 'short_text',
  choice: 'single_choice',
  radio: 'single_choice',
  single: 'single_choice',
  single_choice: 'single_choice',
  select: 'single_choice',
  checkbox: 'multi_choice',
  multi: 'multi_choice',
  multiple: 'multi_choice',
  multiple_choice: 'multi_choice',
  multi_choice: 'multi_choice',
  boolean: 'true_false',
  bool: 'true_false',
  truefalse: 'true_false',
  true_false: 'true_false',
  number: 'number',
};

const normalizeFieldType = (value?: string) => {
  const key = String(value || 'short_text')
    .trim()
    .toLowerCase()
    .replace(/-/g, '_');
  return FIELD_TYPE_ALIASES[key] || key || 'short_text';
};

const cssAttributeEscape = (value: string) => value.replace(/["\\]/g, '\\$&');

const tokuiAttrEscape = (value: string) =>
  value.replace(/\\/g, '\\\\').replace(/"/g, '\\"');

const cleanTokuiTableCell = (value: string) =>
  String(value || '')
    .replace(/\[[^\]]+\]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\\/g, '\\\\')
    .replace(/"/g, "'")
    .replace(/\[/g, '(')
    .replace(/\]/g, ')');

const extractHtmlStyleCells = (rowBody: string, cellTag: 'td' | 'th') => {
  const cells = Array.from(
    rowBody.matchAll(
      new RegExp(`\\[${cellTag}\\b[^\\]]*\\]([\\s\\S]*?)\\[/${cellTag}\\]`, 'gi'),
    ),
  ).map(match => cleanTokuiTableCell(match[1] || ''));
  if (cells.length > 0) {
    return cells.filter(Boolean);
  }
  return Array.from(
    rowBody.matchAll(new RegExp(`\\[${cellTag}\\s+([^\\]]+)\\]`, 'gi')),
  )
    .map(match => cleanTokuiTableCell(match[1] || ''))
    .filter(Boolean);
};

const extractHtmlStyleRows = (tableBody: string, cellTag: 'td' | 'th') =>
  Array.from(tableBody.matchAll(/\[tr\b[^\]]*\]([\s\S]*?)\[\/tr\]/gi))
    .map(match => extractHtmlStyleCells(match[1] || '', cellTag))
    .filter(cells => cells.length > 0);

const repairHtmlStyleTableCells = (match: string, _attrs: string, body: string) => {
  if (!/\[(td|th)(\s|\])/i.test(body)) {
    return match;
  }

  const thead = body.match(/\[thead\b[^\]]*\]([\s\S]*?)\[\/thead\]/i)?.[1] || '';
  const tbody = body.match(/\[tbody\b[^\]]*\]([\s\S]*?)\[\/tbody\]/i)?.[1] || body;
  const headers = extractHtmlStyleRows(thead, 'th')[0] || [];
  const rows = extractHtmlStyleRows(tbody, 'td');
  if (rows.length === 0) {
    return match;
  }

  const cols = rows
    .map(row => {
      const [title, ...cells] = row;
      if (!title) return '';
      const details = cells
        .map((cell, index) => {
          const label = headers[index + 1] || `维度 ${index + 2}`;
          return `[p ${label}：${cell}]`;
        })
        .join('');
      return `[col][badge ${title}]${details}[/col]`;
    })
    .filter(Boolean)
    .join('');
  return cols ? `[row]${cols}[/row]` : match;
};

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
  const required =
    /(?:\brequired\s*=\s*(?:"true"|'true'|true|1)|\brequired\b)/i.test(attrs);
  const tokuiType = fieldType === 'number' ? 'number' : 'text';
  const parts = [`n:"${tokuiAttrEscape(fieldId)}"`, `t:${tokuiType}`];
  if (label) {
    parts.push(`l:"${tokuiAttrEscape(label)}"`);
  }
  if (required) {
    parts.push('req');
  }
  return `[input ${parts.join(' ')}]`;
};

const normalizeLegacyTokuiMediaTag = (attrs: string) => {
  const mediaType = (
    readLegacyTokuiAttr(attrs, 'type') || 'image'
  ).toLowerCase();
  const url =
    readLegacyTokuiAttr(attrs, 'url') || readLegacyTokuiAttr(attrs, 'src');
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
    .replace(/\[table([^\]]*)\]([\s\S]*?)\[\/table\]/gi, repairHtmlStyleTableCells)
    .replace(/\[input\b([^\]]*)\]/gi, (match, attrs) =>
      normalizeLegacyTokuiInputTag(match, attrs),
    )
    .replace(/\[submit\b([^\]]*)\/?\]/gi, (_match, attrs) => {
      const label = readLegacyTokuiAttr(attrs, 'label') || '提交';
      return `[btn tx:"${tokuiAttrEscape(label)}" v:primary act:submit]`;
    })
    .replace(/\[media\b([^\]]*)\/?\]/gi, (_match, attrs) =>
      normalizeLegacyTokuiMediaTag(attrs),
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
    if (
      elements[0] instanceof HTMLInputElement &&
      elements[0].type === 'checkbox'
    ) {
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
    if (
      elements[0] instanceof HTMLInputElement &&
      elements[0].type === 'radio'
    ) {
      elements.forEach(element => {
        if (element instanceof HTMLInputElement) {
          const displayValue =
            typeof value === 'boolean'
              ? String(value)
              : valueToDisplayString(value);
          element.checked = element.value === displayValue;
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

const normalizeOptionValue = (value: unknown) => String(value ?? '').trim();

const optionListForField = (field: TokuiInteractionField) => {
  const fieldType = normalizeFieldType(field.field_type);
  if (fieldType === 'true_false') {
    return [
      { value: 'true', label: '对' },
      { value: 'false', label: '错' },
    ];
  }
  if (!Array.isArray(field.options)) return [];
  return field.options
    .map(option => ({
      value: normalizeOptionValue(option.value),
      label: String(option.label || option.value || '').trim(),
    }))
    .filter(option => option.value || option.label)
    .map(option => ({
      value: option.value || option.label,
      label: option.label || option.value,
    }));
};

const createFallbackControl = (
  root: HTMLDivElement,
  field: TokuiInteractionField,
) => {
  const doc = root.ownerDocument;
  const fieldType = normalizeFieldType(field.field_type);
  const wrapper = doc.createElement('div');
  wrapper.className = 'tokui-schema-control';
  const label = doc.createElement('label');
  label.className = 'tokui-schema-control__label';
  label.textContent = field.label || field.field_id;
  wrapper.appendChild(label);

  if (fieldType === 'single_choice' || fieldType === 'true_false') {
    const group = doc.createElement('div');
    group.className = 'tokui-schema-control__options';
    optionListForField(field).forEach(option => {
      const optionLabel = doc.createElement('label');
      optionLabel.className = 'tokui-schema-control__option';
      const input = doc.createElement('input');
      input.type = 'radio';
      input.name = field.field_id;
      input.value = option.value;
      input.required = Boolean(field.required);
      optionLabel.appendChild(input);
      optionLabel.append(` ${option.label}`);
      group.appendChild(optionLabel);
    });
    wrapper.appendChild(group);
    return wrapper;
  }

  if (fieldType === 'multi_choice') {
    const group = doc.createElement('div');
    group.className = 'tokui-schema-control__options';
    optionListForField(field).forEach(option => {
      const optionLabel = doc.createElement('label');
      optionLabel.className = 'tokui-schema-control__option';
      const input = doc.createElement('input');
      input.type = 'checkbox';
      input.name = field.field_id;
      input.value = option.value;
      optionLabel.appendChild(input);
      optionLabel.append(` ${option.label}`);
      group.appendChild(optionLabel);
    });
    wrapper.appendChild(group);
    return wrapper;
  }

  const textarea = doc.createElement('textarea');
  textarea.name = field.field_id;
  textarea.required = Boolean(field.required);
  textarea.placeholder = field.label || '请输入你的答案';
  wrapper.appendChild(textarea);
  return wrapper;
};

const ensureSchemaFallbackControls = (
  root: HTMLDivElement,
  interactionSchema: TokuiInteractionField[],
) => {
  const missingFields = interactionSchema.filter(
    field =>
      field.field_id && findFieldElements(root, field.field_id).length === 0,
  );
  if (!missingFields.length) return;
  const doc = root.ownerDocument;
  const form = doc.createElement('form');
  form.className = 'tokui-schema-fallback';
  form.dataset.tokuiTag = 'form';
  missingFields.forEach(field => {
    form.appendChild(createFallbackControl(root, field));
  });
  const button = doc.createElement('button');
  button.type = 'submit';
  button.className = 'tokui-btn tokui-schema-fallback__submit';
  button.dataset.tokuiTag = 'btn';
  button.dataset.tokuiAct = 'submit';
  button.textContent = '提交';
  form.appendChild(button);
  root.appendChild(form);
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
  const fieldType = normalizeFieldType(field.field_type);
  if (
    elements[0] instanceof HTMLInputElement &&
    elements[0].type === 'checkbox'
  ) {
    const checked = elements
      .filter(element => element instanceof HTMLInputElement && element.checked)
      .map(element => element.value || true);
    return fieldType === 'multi_choice' || elements.length > 1
      ? checked
      : Boolean(elements[0].checked);
  }
  if (elements[0] instanceof HTMLInputElement && elements[0].type === 'radio') {
    const checked = elements.find(
      element => element instanceof HTMLInputElement && element.checked,
    );
    if (!checked) return undefined;
    if (fieldType === 'true_false') {
      return checked.value === 'true';
    }
    return checked.value;
  }
  if (fieldType === 'true_false') {
    const value = elements[0].value;
    if (value === 'true') return true;
    if (value === 'false') return false;
  }
  return elements[0].value;
};

export default function TokuiRenderer({
  dsl,
  interactionSchema = [],
  theme = 'modern',
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
    ensureSchemaFallbackControls(root, latestRenderState.interactionSchema);
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
    ensureSchemaFallbackControls(root, interactionSchema);
    applySubmittedResponses(root, submittedResponses);
    setReadOnlyState(root, readOnly);
  }, [dsl, interactionSchema, readOnly, submittedResponses]);

  const submitResponses = useCallback(() => {
    if (readOnly || !rootRef.current || !onSubmitResponses) return;
    const responses = interactionSchema
      .map(field => ({
        field_id: field.field_id,
        field_type: normalizeFieldType(field.field_type),
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
      className={['tokui-course-renderer', className].filter(Boolean).join(' ')}
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
    ></div>
  );
}

export function TokuiStreamingRenderer({
  chunks,
  streamKey,
  complete = false,
  theme = 'modern',
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
      className={['tokui-course-renderer', className].filter(Boolean).join(' ')}
    />
  );
}
