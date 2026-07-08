import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import api from '@/api';
import LearnerTokuiBlock from './LearnerTokuiBlock';
import { streamLearnerTokui } from './learnerTokuiStream';

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getLearnerTokui: jest.fn(),
    retryLearnerTokui: jest.fn(),
    saveLearnerTokuiResponses: jest.fn(),
  },
}));

jest.mock('./learnerTokuiStream', () => ({
  streamLearnerTokui: jest.fn(),
}));

const mockT = (key: string) => key;

jest.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: mockT,
  }),
}));

jest.mock('@/hooks/useToast', () => ({
  toast: jest.fn(),
}));

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

const mockedApi = api as jest.Mocked<typeof api>;
const mockedStreamLearnerTokui =
  streamLearnerTokui as jest.MockedFunction<typeof streamLearnerTokui>;

const mockTokuiStreamFinal = (artifact: unknown) => {
  mockedStreamLearnerTokui.mockImplementationOnce(({ onEvent, onDone }) => {
    Promise.resolve().then(() => {
      onEvent({ type: 'final', artifact });
      onDone?.();
    });
    return { close: jest.fn() };
  });
};

describe('LearnerTokuiBlock continuation flow', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('keeps submitted content visible while appending continuation output', async () => {
    let resolveRetry:
      | ((value: {
          enabled: boolean;
          tokui_artifact_bid: string;
          schema_hash: string;
          validation_status: string;
          dsl: string;
          interaction_schema: unknown[];
        }) => void)
      | undefined;

    mockTokuiStreamFinal({
      enabled: true,
      artifact_chain: [
        {
          tokui_artifact_bid: 'artifact-1',
          schema_hash: 'schema-1',
          validation_status: 'validated',
          dsl: `
            <section>
              <p>第一段讲解</p>
              <form>
                <textarea name="heavy_haul_answer">请输入你的答案</textarea>
                <button class="tokui-btn" type="button" data-tokui-tag="btn">
                  提交答案
                </button>
              </form>
            </section>
          `,
          interaction_schema: [
            {
              field_id: 'heavy_haul_answer',
              field_type: 'text',
              blocking: true,
              continue_on_submit: true,
            },
          ],
        },
      ],
    });
    mockedApi.saveLearnerTokuiResponses.mockResolvedValue({
      continue_required: true,
      continue_fields: ['heavy_haul_answer'],
    });
    mockedStreamLearnerTokui.mockImplementationOnce(({ onEvent, onDone }) => {
      Promise.resolve().then(() => {
        onEvent({
          type: 'chunk',
          tokui: '<section><p>正在按你的回答继续</p></section>',
        });
      });
      resolveRetry = value => {
        onEvent({ type: 'final', artifact: value });
        onDone?.();
      };
      return { close: jest.fn() };
    });

    render(
      <LearnerTokuiBlock shifuBid='shifu-1' outlineBid='outline-1' />,
    );

    expect(await screen.findByText('第一段讲解')).toBeInTheDocument();

    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: '重载铁路' },
    });
    fireEvent.click(screen.getByRole('button', { name: '提交答案' }));

    await waitFor(() => {
      expect(mockedApi.saveLearnerTokuiResponses).toHaveBeenCalledWith(
        expect.objectContaining({
          tokui_artifact_bid: 'artifact-1',
          responses: [
            {
              field_id: 'heavy_haul_answer',
              field_type: 'text',
              value: '重载铁路',
            },
          ],
        }),
      );
    });

    expect(screen.getByText('第一段讲解')).toBeInTheDocument();
    expect(screen.getByDisplayValue('重载铁路')).toHaveAttribute('readonly');
    expect(screen.getByText('已提交，答案会用于后续讲解。')).toBeInTheDocument();
    expect(
      screen.getByText('已提交，正在根据你的回答继续讲解...'),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(mockedStreamLearnerTokui).toHaveBeenLastCalledWith(
        expect.objectContaining({
          shifuBid: 'shifu-1',
          outlineBid: 'outline-1',
          forceRegenerate: true,
        }),
      );
    });
    expect(
      await screen.findByText('正在按你的回答继续'),
    ).toBeInTheDocument();

    await act(async () => {
      resolveRetry?.({
        enabled: true,
        tokui_artifact_bid: 'artifact-2',
        schema_hash: 'schema-2',
        validation_status: 'validated',
        dsl: '<section><p>第二段：根据你的回答继续讲解</p></section>',
        interaction_schema: [],
      });
    });

    expect(
      await screen.findByText('第二段：根据你的回答继续讲解'),
    ).toBeInTheDocument();
    expect(screen.getByText('第一段讲解')).toBeInTheDocument();
    expect(screen.getByDisplayValue('重载铁路')).toHaveAttribute('readonly');
  });

  it('keeps prior content visible and shows retry fallback when continuation fails', async () => {
    mockTokuiStreamFinal({
      enabled: true,
      tokui_artifact_bid: 'artifact-1',
      schema_hash: 'schema-1',
      validation_status: 'validated',
      dsl: `
        <section>
          <p>第一段讲解</p>
          <form>
            <textarea name="heavy_haul_answer">请输入你的答案</textarea>
            <button class="tokui-btn" type="button" data-tokui-tag="btn">
              提交答案
            </button>
          </form>
        </section>
      `,
      interaction_schema: [
        {
          field_id: 'heavy_haul_answer',
          field_type: 'text',
          blocking: true,
          continue_on_submit: true,
        },
      ],
    });
    mockedApi.saveLearnerTokuiResponses.mockResolvedValue({
      continue_required: true,
      continue_fields: ['heavy_haul_answer'],
    });
    mockedStreamLearnerTokui.mockImplementationOnce(({ onError }) => {
      Promise.resolve().then(() => onError?.(new Error('retry failed')));
      return { close: jest.fn() };
    });

    render(
      <LearnerTokuiBlock shifuBid='shifu-1' outlineBid='outline-1' />,
    );

    expect(await screen.findByText('第一段讲解')).toBeInTheDocument();

    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: '重载铁路' },
    });
    fireEvent.click(screen.getByRole('button', { name: '提交答案' }));

    await waitFor(() =>
      expect(mockedStreamLearnerTokui).toHaveBeenCalledTimes(2),
    );

    expect(screen.getByText('第一段讲解')).toBeInTheDocument();
    expect(screen.getByDisplayValue('重载铁路')).toHaveAttribute('readonly');
    expect(screen.getByText('module.chat.tokuiLoadFailed')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'module.chat.tokuiRetry' }),
    ).toBeInTheDocument();
  });

  it('restores editable answers when saving responses fails', async () => {
    mockTokuiStreamFinal({
      enabled: true,
      tokui_artifact_bid: 'artifact-1',
      schema_hash: 'schema-1',
      validation_status: 'validated',
      dsl: `
        <section>
          <p>第一段讲解</p>
          <form>
            <textarea name="heavy_haul_answer">请输入你的答案</textarea>
            <button class="tokui-btn" type="button" data-tokui-tag="btn">
              提交答案
            </button>
          </form>
        </section>
      `,
      interaction_schema: [
        {
          field_id: 'heavy_haul_answer',
          field_type: 'text',
          blocking: true,
          continue_on_submit: true,
        },
      ],
    });
    mockedApi.saveLearnerTokuiResponses.mockRejectedValue(new Error('save failed'));

    render(
      <LearnerTokuiBlock shifuBid='shifu-1' outlineBid='outline-1' />,
    );

    expect(await screen.findByText('第一段讲解')).toBeInTheDocument();

    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: '包含换行\n和符号 [] " 的答案' },
    });
    fireEvent.click(screen.getByRole('button', { name: '提交答案' }));

    await waitFor(() => {
      expect(mockedApi.saveLearnerTokuiResponses).toHaveBeenCalledWith(
        expect.objectContaining({
          responses: [
            {
              field_id: 'heavy_haul_answer',
              field_type: 'text',
              value: '包含换行\n和符号 [] " 的答案',
            },
          ],
        }),
      );
    });
    expect(mockedStreamLearnerTokui).toHaveBeenCalledTimes(1);

    await waitFor(() => {
      const textbox = screen.getByRole('textbox') as HTMLTextAreaElement;
      expect(textbox.textContent).toBe('包含换行\n和符号 [] " 的答案');
      expect(textbox).not.toHaveAttribute('readonly');
    });
    expect(mockedStreamLearnerTokui).toHaveBeenCalledTimes(1);
  });

  it('ignores duplicate submit clicks while the first save is pending', async () => {
    mockTokuiStreamFinal({
      enabled: true,
      tokui_artifact_bid: 'artifact-1',
      schema_hash: 'schema-1',
      validation_status: 'validated',
      dsl: `
        <section>
          <p>第一段讲解</p>
          <form>
            <textarea name="heavy_haul_answer">请输入你的答案</textarea>
            <button class="tokui-btn" type="button" data-tokui-tag="btn">
              提交答案
            </button>
          </form>
        </section>
      `,
      interaction_schema: [
        {
          field_id: 'heavy_haul_answer',
          field_type: 'text',
          blocking: false,
          continue_on_submit: false,
        },
      ],
    });
    mockedApi.saveLearnerTokuiResponses.mockReturnValue(new Promise(() => {}));

    render(
      <LearnerTokuiBlock shifuBid='shifu-1' outlineBid='outline-1' />,
    );

    expect(await screen.findByText('第一段讲解')).toBeInTheDocument();
    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: '重载铁路' },
    });

    const button = screen.getByRole('button', { name: '提交答案' });
    fireEvent.click(button);
    fireEvent.click(button);

    expect(mockedApi.saveLearnerTokuiResponses).toHaveBeenCalledTimes(1);
  });

  it('renders all artifacts returned by backend artifact_chain', async () => {
    mockTokuiStreamFinal({
      enabled: true,
      artifact_chain: [
        {
          tokui_artifact_bid: 'artifact-1',
          schema_hash: 'schema-1',
          validation_status: 'validated',
          submitted: true,
          submitted_responses: [
            {
              field_id: 'heavy_haul_answer',
              field_type: 'text',
              value: '重载铁路',
            },
          ],
          dsl: `
            <section>
              <p>第一段讲解</p>
              <form>
                <textarea name="heavy_haul_answer">请输入你的答案</textarea>
                <button class="tokui-btn" type="button" data-tokui-tag="btn">
                  提交答案
                </button>
              </form>
            </section>
          `,
          interaction_schema: [
            {
              field_id: 'heavy_haul_answer',
              field_type: 'text',
              blocking: true,
              continue_on_submit: true,
            },
          ],
        },
        {
          enabled: true,
          tokui_artifact_bid: 'artifact-2',
          schema_hash: 'schema-2',
          validation_status: 'validated',
          dsl: '<section><p>第二段继续讲解</p></section>',
          interaction_schema: [],
        },
      ],
    });

    render(
      <LearnerTokuiBlock shifuBid='shifu-1' outlineBid='outline-1' />,
    );

    expect(await screen.findByText('第一段讲解')).toBeInTheDocument();
    expect(screen.getByText('第二段继续讲解')).toBeInTheDocument();
    expect(screen.getByDisplayValue('重载铁路')).toHaveAttribute('readonly');
  });
});
