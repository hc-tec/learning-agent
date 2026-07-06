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
});
