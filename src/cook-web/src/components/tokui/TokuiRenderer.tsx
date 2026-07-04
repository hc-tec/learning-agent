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

const readFieldValue = (root: HTMLDivElement, field: TokuiInteractionField) => {
  const selector = `[name="${CSS.escape(field.field_id)}"], #${CSS.escape(field.field_id)}`;
  const elements = Array.from(
    root.querySelectorAll<
      HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
    >(selector),
  );
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
      className={className}
      onSubmit={event => {
        event.preventDefault();
        submitResponses();
      }}
      onClick={event => {
        const target = event.target as HTMLElement | null;
        if (
          target?.closest('button[type="submit"], [data-tokui-act="submit"]')
        ) {
          submitResponses();
        }
      }}
    >
    </div>
  );
}
