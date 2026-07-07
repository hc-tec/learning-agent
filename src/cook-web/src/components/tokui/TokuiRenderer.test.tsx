import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import TokuiRenderer from './TokuiRenderer';

jest.mock('@jboltai/tokui', () => ({
  TokUI: class {
    private container: HTMLElement;

    constructor({ container }: { container: HTMLElement }) {
      this.container = container;
    }

    render(dsl: string) {
      this.container.innerHTML = dsl;
    }

    disconnect() {}
  },
  setTheme: jest.fn(),
}));

describe('TokuiRenderer response submission', () => {
  it('submits form values when TokUI renders a type button submit control', () => {
    const handleSubmit = jest.fn();
    const { container } = render(
      <TokuiRenderer
        dsl={`
          <form class="tokui-form" data-tokui-tag="form">
            <textarea name="heavy_haul_answer">请输入你的答案</textarea>
            <textarea name="intercity_answer">Please enter your answer</textarea>
            <button class="tokui-btn" type="button" data-tokui-tag="btn">
              <span class="tokui-btn__text">提交答案</span>
            </button>
          </form>
        `}
        interactionSchema={[
          { field_id: 'heavy_haul_answer', field_type: 'text' },
          { field_id: 'intercity_answer', field_type: 'text' },
        ]}
        onSubmitResponses={handleSubmit}
      />,
    );

    fireEvent.change(
      container.querySelector(
        'textarea[name="heavy_haul_answer"]',
      ) as HTMLTextAreaElement,
      { target: { value: '重载铁路' } },
    );
    fireEvent.change(
      container.querySelector(
        'textarea[name="intercity_answer"]',
      ) as HTMLTextAreaElement,
      { target: { value: '城际铁路' } },
    );
    fireEvent.click(screen.getByRole('button', { name: '提交答案' }));

    expect(handleSubmit).toHaveBeenCalledWith([
      {
        field_id: 'heavy_haul_answer',
        field_type: 'text',
        value: '重载铁路',
      },
      {
        field_id: 'intercity_answer',
        field_type: 'text',
        value: '城际铁路',
      },
    ]);
  });

  it('turns generated textarea prompt text into placeholders', () => {
    const { container } = render(
      <TokuiRenderer
        dsl={`
          <form class="tokui-form" data-tokui-tag="form">
            <textarea name="answer">请输入你的答案</textarea>
          </form>
        `}
        interactionSchema={[{ field_id: 'answer', field_type: 'text' }]}
        onSubmitResponses={jest.fn()}
      />,
    );

    const textarea = container.querySelector(
      'textarea[name="answer"]',
    ) as HTMLTextAreaElement;

    expect(textarea.value).toBe('');
    expect(textarea.placeholder).toBe('请输入你的答案');
  });

  it('does not wipe in-progress answers on parent rerender', () => {
    const dsl = `
      <form class="tokui-form" data-tokui-tag="form">
        <textarea name="answer">请输入你的答案</textarea>
      </form>
    `;
    const { container, rerender } = render(
      <TokuiRenderer
        dsl={dsl}
        interactionSchema={[{ field_id: 'answer', field_type: 'text' }]}
        onSubmitResponses={jest.fn()}
      />,
    );
    const textarea = container.querySelector(
      'textarea[name="answer"]',
    ) as HTMLTextAreaElement;

    fireEvent.change(textarea, { target: { value: '还没提交的答案' } });
    rerender(
      <TokuiRenderer
        dsl={dsl}
        interactionSchema={[{ field_id: 'answer', field_type: 'text' }]}
        onSubmitResponses={jest.fn()}
      />,
    );

    expect(textarea.value).toBe('还没提交的答案');
  });

  it('ignores TokUI buttons that are not inside a form', () => {
    const handleSubmit = jest.fn();
    render(
      <TokuiRenderer
        dsl={`
          <textarea name="heavy_haul_answer">重载铁路</textarea>
          <button class="tokui-btn" type="button" data-tokui-tag="btn">
            提交答案
          </button>
        `}
        interactionSchema={[
          { field_id: 'heavy_haul_answer', field_type: 'text' },
        ]}
        onSubmitResponses={handleSubmit}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '提交答案' }));

    expect(handleSubmit).not.toHaveBeenCalled();
  });

  it('reads fields by id without treating punctuation as a CSS selector', () => {
    const handleSubmit = jest.fn();
    render(
      <TokuiRenderer
        dsl={`
          <form class="tokui-form" data-tokui-tag="form">
            <input id="answer.with.dot" value="按 id 读取" />
            <button class="tokui-btn" type="button" data-tokui-tag="btn">
              提交答案
            </button>
          </form>
        `}
        interactionSchema={[{ field_id: 'answer.with.dot', field_type: 'text' }]}
        onSubmitResponses={handleSubmit}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '提交答案' }));

    expect(handleSubmit).toHaveBeenCalledWith([
      {
        field_id: 'answer.with.dot',
        field_type: 'text',
        value: '按 id 读取',
      },
    ]);
  });

  it('renders submitted responses in read-only mode without resubmitting', () => {
    const handleSubmit = jest.fn();
    const { container } = render(
      <TokuiRenderer
        dsl={`
          <form class="tokui-form" data-tokui-tag="form">
            <textarea name="heavy_haul_answer">请输入你的答案</textarea>
            <button class="tokui-btn" type="button" data-tokui-tag="btn">
              提交答案
            </button>
          </form>
        `}
        interactionSchema={[
          { field_id: 'heavy_haul_answer', field_type: 'text' },
        ]}
        submittedResponses={[
          {
            field_id: 'heavy_haul_answer',
            field_type: 'text',
            value: '重载铁路',
          },
        ]}
        readOnly
        onSubmitResponses={handleSubmit}
      />,
    );

    const textarea = container.querySelector(
      'textarea[name="heavy_haul_answer"]',
    ) as HTMLTextAreaElement;

    expect(textarea.value).toBe('重载铁路');
    expect(textarea).toHaveAttribute('readonly');
    expect(screen.getByRole('button', { name: '提交答案' })).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: '提交答案' }));

    expect(handleSubmit).not.toHaveBeenCalled();
  });

  it('restores submitted responses without forcing read-only mode', () => {
    const { container } = render(
      <TokuiRenderer
        dsl={`
          <form class="tokui-form" data-tokui-tag="form">
            <textarea name="heavy_haul_answer">请输入你的答案</textarea>
          </form>
        `}
        interactionSchema={[
          { field_id: 'heavy_haul_answer', field_type: 'text' },
        ]}
        submittedResponses={[
          {
            field_id: 'heavy_haul_answer',
            field_type: 'text',
            value: '包含换行\n和符号 [] " 的答案',
          },
        ]}
        onSubmitResponses={jest.fn()}
      />,
    );

    const textarea = container.querySelector(
      'textarea[name="heavy_haul_answer"]',
    ) as HTMLTextAreaElement;

    expect(textarea.value).toBe('包含换行\n和符号 [] " 的答案');
    expect(textarea).not.toHaveAttribute('readonly');
  });

  it('submits and restores checkbox radio and select answers', () => {
    const handleSubmit = jest.fn();
    const { container, rerender } = render(
      <TokuiRenderer
        dsl={`
          <form class="tokui-form" data-tokui-tag="form">
            <label><input type="checkbox" name="topics" value="speed" />速度</label>
            <label><input type="checkbox" name="topics" value="cargo" />货运</label>
            <label><input type="radio" name="railway_type" value="heavy" />重载</label>
            <label><input type="radio" name="railway_type" value="intercity" />城际</label>
            <select name="confidence">
              <option value="low">低</option>
              <option value="high">高</option>
            </select>
            <button class="tokui-btn" type="button" data-tokui-tag="btn">
              提交答案
            </button>
          </form>
        `}
        interactionSchema={[
          { field_id: 'topics', field_type: 'checkbox' },
          { field_id: 'railway_type', field_type: 'radio' },
          { field_id: 'confidence', field_type: 'select' },
        ]}
        onSubmitResponses={handleSubmit}
      />,
    );

    fireEvent.click(
      container.querySelector('input[name="topics"][value="speed"]') as Element,
    );
    fireEvent.click(
      container.querySelector('input[name="topics"][value="cargo"]') as Element,
    );
    fireEvent.click(
      container.querySelector(
        'input[name="railway_type"][value="heavy"]',
      ) as Element,
    );
    fireEvent.change(
      container.querySelector('select[name="confidence"]') as HTMLSelectElement,
      { target: { value: 'high' } },
    );
    fireEvent.click(screen.getByRole('button', { name: '提交答案' }));

    expect(handleSubmit).toHaveBeenCalledWith([
      { field_id: 'topics', field_type: 'checkbox', value: ['speed', 'cargo'] },
      { field_id: 'railway_type', field_type: 'radio', value: 'heavy' },
      { field_id: 'confidence', field_type: 'select', value: 'high' },
    ]);

    rerender(
      <TokuiRenderer
        dsl={`
          <form class="tokui-form" data-tokui-tag="form">
            <label><input type="checkbox" name="topics" value="speed" />速度</label>
            <label><input type="checkbox" name="topics" value="cargo" />货运</label>
            <label><input type="radio" name="railway_type" value="heavy" />重载</label>
            <label><input type="radio" name="railway_type" value="intercity" />城际</label>
            <select name="confidence">
              <option value="low">低</option>
              <option value="high">高</option>
            </select>
            <button class="tokui-btn" type="button" data-tokui-tag="btn">
              提交答案
            </button>
          </form>
        `}
        interactionSchema={[
          { field_id: 'topics', field_type: 'checkbox' },
          { field_id: 'railway_type', field_type: 'radio' },
          { field_id: 'confidence', field_type: 'select' },
        ]}
        submittedResponses={[
          { field_id: 'topics', field_type: 'checkbox', value: ['cargo'] },
          { field_id: 'railway_type', field_type: 'radio', value: 'intercity' },
          { field_id: 'confidence', field_type: 'select', value: 'low' },
        ]}
        readOnly
        onSubmitResponses={handleSubmit}
      />,
    );

    expect(
      container.querySelector('input[name="topics"][value="speed"]'),
    ).not.toBeChecked();
    expect(
      container.querySelector('input[name="topics"][value="cargo"]'),
    ).toBeChecked();
    expect(
      container.querySelector(
        'input[name="railway_type"][value="intercity"]',
      ),
    ).toBeChecked();
    expect(
      container.querySelector('select[name="confidence"]'),
    ).toHaveValue('low');
    expect(container.querySelector('select[name="confidence"]')).toBeDisabled();
  });
});
