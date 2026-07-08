import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import TokuiRenderer, { normalizeLearnerTokuiDsl } from './TokuiRenderer';

jest.mock('@jboltai/tokui', () => ({
  TokUI: class {
    private container: HTMLElement;

    constructor({ container }: { container: HTMLElement }) {
      this.container = container;
    }

    render(dsl: string) {
      this.container.innerHTML = dsl;
    }

    startStream() {
      this.container.innerHTML = '';
    }

    feed(chunk: string) {
      this.container.insertAdjacentHTML('beforeend', chunk);
    }

    endStream() {}

    disconnect() {}
  },
  setTheme: jest.fn(),
}));

describe('TokuiRenderer response submission', () => {
  it('renders reference-style TokUI panels together with explanatory text and choices', () => {
    const { container } = render(
      <TokuiRenderer
        dsl={`
          <section data-tokui-tag="card">
            <p>先用文字解释四类铁路为什么要区分。</p>
            <div data-tokui-tag="row">
              <div data-tokui-tag="col">
                <span data-tokui-tag="badge">高速铁路</span>
                <p>长途主干客运</p>
              </div>
              <div data-tokui-tag="col">
                <span data-tokui-tag="badge">重载铁路</span>
                <p>大宗货运</p>
              </div>
            </div>
            <form class="tokui-form" data-tokui-tag="form">
              <label><input type="radio" name="railway_type" value="heavy_haul" />重载铁路</label>
              <button class="tokui-btn" type="button" data-tokui-tag="btn">提交</button>
            </form>
          </section>
        `}
        interactionSchema={[
          { field_id: 'railway_type', field_type: 'single_choice' },
        ]}
        onSubmitResponses={jest.fn()}
      />,
    );

    expect(container.querySelector('[data-tokui-tag="row"]')).toBeTruthy();
    expect(container.querySelectorAll('[data-tokui-tag="col"]')).toHaveLength(2);
    expect(container.querySelectorAll('[data-tokui-tag="badge"]')).toHaveLength(
      2,
    );
    expect(container).toHaveTextContent('先用文字解释四类铁路为什么要区分。');
  });

  it('annotates valid TokUI tables so CSS can render comparison cards with labels', () => {
    const { container } = render(
      <TokuiRenderer
        dsl={`
          <table class="tokui-table">
            <thead><tr><th>类型</th><th>速度</th><th>功能</th></tr></thead>
            <tr data-tokui-tag="tr"><td>高速铁路</td><td>250-350 km/h</td><td>长途客运</td></tr>
            <tr data-tokui-tag="tr"><td>城际铁路</td><td>100-200 km/h</td><td>通勤</td></tr>
            <tr data-tokui-tag="tr"><td>重载铁路</td><td>80-120 km/h</td><td>大宗货运</td></tr>
          </table>
        `}
      />,
    );

    const table = container.querySelector('.tokui-table') as HTMLElement;
    const firstDataCell = container.querySelectorAll('td')[1] as HTMLElement;

    expect(table.dataset.tokuiVisual).toBe('comparison');
    expect(firstDataCell.dataset.tokuiCol).toBe('速度');
  });

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
        field_type: 'short_text',
        value: '重载铁路',
      },
      {
        field_id: 'intercity_answer',
        field_type: 'short_text',
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

  it('normalizes legacy learner DSL aliases before rendering', () => {
    expect(
      normalizeLearnerTokuiDsl(
        '[input field_id="answer" field_type="text" label="你的答案" required=true][submit label="提交"]',
      ),
    ).toBe(
      '[input n:"answer" t:text l:"你的答案" req][btn tx:"提交" v:primary act:submit]',
    );
  });

  it('normalizes legacy media tags into supported TokUI nodes or placeholders', () => {
    expect(
      normalizeLearnerTokuiDsl(
        '[media type="image" url="/figure.png" title="参数对比图"][media type="video" url="" title="实景短片"]',
      ),
    ).toBe(
      '[img s:"/figure.png" tt:"参数对比图" alt:"参数对比图"][p v:muted 素材待提供：实景短片]',
    );
  });

  it('normalizes HTML-style TokUI table cells into comparison cards', () => {
    expect(
      normalizeLearnerTokuiDsl(
        '[table][thead][tr][th 类型][th 速度][th 功能][/tr][/thead]' +
          '[tbody][tr][td 高速铁路][td 250-350 km/h][td 长途纯客运][/tr]' +
          '[tr][td 重载铁路][td 80-120 km/h][td 大宗货运][/tr][/tbody][/table]',
      ),
    ).toBe(
      '[row][col][badge 高速铁路][p 速度：250-350 km/h][p 功能：长途纯客运][/col]' +
        '[col][badge 重载铁路][p 速度：80-120 km/h][p 功能：大宗货运][/col][/row]',
    );
  });

  it('ignores non-submit TokUI buttons that are not inside a form', () => {
    const handleSubmit = jest.fn();
    render(
      <TokuiRenderer
        dsl={`
          <textarea name="heavy_haul_answer">重载铁路</textarea>
          <button class="tokui-btn" type="button" data-tokui-tag="btn">
            查看提示
          </button>
        `}
        interactionSchema={[
          { field_id: 'heavy_haul_answer', field_type: 'text' },
        ]}
        onSubmitResponses={handleSubmit}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '查看提示' }));

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
        interactionSchema={[
          { field_id: 'answer.with.dot', field_type: 'text' },
        ]}
        onSubmitResponses={handleSubmit}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '提交答案' }));

    expect(handleSubmit).toHaveBeenCalledWith([
      {
        field_id: 'answer.with.dot',
        field_type: 'short_text',
        value: '按 id 读取',
      },
    ]);
  });

  it('assigns schema field names to generated unnamed controls', () => {
    const handleSubmit = jest.fn();
    const { container } = render(
      <TokuiRenderer
        dsl={`
          <form class="tokui-form" data-tokui-tag="form">
            <input value="" />
            <button class="tokui-btn" type="button" data-tokui-tag="btn">
              提交
            </button>
          </form>
        `}
        interactionSchema={[
          { field_id: 'heavy_haul_reason_check', field_type: 'text' },
        ]}
        onSubmitResponses={handleSubmit}
      />,
    );

    const input = container.querySelector('input') as HTMLInputElement;
    expect(input.name).toBe('heavy_haul_reason_check');
    fireEvent.change(input, { target: { value: '高铁线路按高速客运优化' } });
    fireEvent.click(screen.getByRole('button', { name: '提交' }));

    expect(handleSubmit).toHaveBeenCalledWith([
      {
        field_id: 'heavy_haul_reason_check',
        field_type: 'short_text',
        value: '高铁线路按高速客运优化',
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
      {
        field_id: 'topics',
        field_type: 'multi_choice',
        value: ['speed', 'cargo'],
      },
      { field_id: 'railway_type', field_type: 'single_choice', value: 'heavy' },
      { field_id: 'confidence', field_type: 'single_choice', value: 'high' },
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
      container.querySelector('input[name="railway_type"][value="intercity"]'),
    ).toBeChecked();
    expect(container.querySelector('select[name="confidence"]')).toHaveValue(
      'low',
    );
    expect(container.querySelector('select[name="confidence"]')).toBeDisabled();
  });

  it('submits canonical rich question types and converts true_false values', () => {
    const handleSubmit = jest.fn();
    const { container } = render(
      <TokuiRenderer
        dsl={`
          <form class="tokui-form" data-tokui-tag="form">
            <textarea name="reason"></textarea>
            <label><input type="radio" name="railway_type" value="heavy" />重载</label>
            <label><input type="radio" name="railway_type" value="intercity" />城际</label>
            <label><input type="checkbox" name="features" value="cargo" />货运</label>
            <label><input type="checkbox" name="features" value="commute" />通勤</label>
            <label><input type="radio" name="is_cargo_only" value="true" />对</label>
            <label><input type="radio" name="is_cargo_only" value="false" />错</label>
            <button class="tokui-btn" type="button" data-tokui-tag="btn">
              提交答案
            </button>
          </form>
        `}
        interactionSchema={[
          { field_id: 'reason', field_type: 'short_text' },
          { field_id: 'railway_type', field_type: 'single_choice' },
          { field_id: 'features', field_type: 'multi_choice' },
          { field_id: 'is_cargo_only', field_type: 'true_false' },
        ]}
        onSubmitResponses={handleSubmit}
      />,
    );

    fireEvent.change(
      container.querySelector('textarea[name="reason"]') as HTMLTextAreaElement,
      { target: { value: '万吨列车对应重载铁路' } },
    );
    fireEvent.click(
      container.querySelector(
        'input[name="railway_type"][value="heavy"]',
      ) as Element,
    );
    fireEvent.click(
      container.querySelector(
        'input[name="features"][value="cargo"]',
      ) as Element,
    );
    fireEvent.click(
      container.querySelector(
        'input[name="is_cargo_only"][value="true"]',
      ) as Element,
    );
    fireEvent.click(screen.getByRole('button', { name: '提交答案' }));

    expect(handleSubmit).toHaveBeenCalledWith([
      {
        field_id: 'reason',
        field_type: 'short_text',
        value: '万吨列车对应重载铁路',
      },
      { field_id: 'railway_type', field_type: 'single_choice', value: 'heavy' },
      { field_id: 'features', field_type: 'multi_choice', value: ['cargo'] },
      { field_id: 'is_cargo_only', field_type: 'true_false', value: true },
    ]);
  });

  it('renders schema fallback controls when DSL misses a declared interaction', () => {
    const handleSubmit = jest.fn();
    render(
      <TokuiRenderer
        dsl='<p>先读完这段讲解，再回答下面的问题。</p>'
        interactionSchema={[
          {
            field_id: 'type_check',
            field_type: 'single_choice',
            label: '万吨列车属于哪类铁路？',
            options: [
              { value: 'high_speed', label: '高速铁路' },
              { value: 'heavy_haul', label: '重载铁路' },
            ],
          },
        ]}
        onSubmitResponses={handleSubmit}
      />,
    );

    fireEvent.click(screen.getByLabelText(/重载铁路/));
    fireEvent.click(screen.getByRole('button', { name: '提交' }));

    expect(handleSubmit).toHaveBeenCalledWith([
      {
        field_id: 'type_check',
        field_type: 'single_choice',
        value: 'heavy_haul',
      },
    ]);
  });
});
