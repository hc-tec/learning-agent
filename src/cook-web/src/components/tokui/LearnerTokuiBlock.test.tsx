import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import api from '@/api';
import LearnerTokuiBlock from './LearnerTokuiBlock';

jest.mock('@/api', () => ({
  __esModule: true,
  default: {
    getLearnerTokui: jest.fn(),
    retryLearnerTokui: jest.fn(),
    saveLearnerTokuiResponses: jest.fn(),
  },
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

    disconnect() {}
  },
  setTheme: jest.fn(),
}));

const mockedApi = api as jest.Mocked<typeof api>;

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

    mockedApi.getLearnerTokui.mockResolvedValue({
      enabled: true,
      artifact_chain: [
        {
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
        },
      ],
    });
    mockedApi.saveLearnerTokuiResponses.mockResolvedValue({
      continue_required: true,
      continue_fields: ['heavy_haul_answer'],
    });
    mockedApi.retryLearnerTokui.mockReturnValue(
      new Promise(resolve => {
        resolveRetry = resolve;
      }),
    );

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

    resolveRetry?.({
      enabled: true,
      tokui_artifact_bid: 'artifact-2',
      schema_hash: 'schema-2',
      validation_status: 'validated',
      dsl: '<section><p>第二段：根据你的回答继续讲解</p></section>',
      interaction_schema: [],
    });

    expect(
      await screen.findByText('第二段：根据你的回答继续讲解'),
    ).toBeInTheDocument();
    expect(screen.getByText('第一段讲解')).toBeInTheDocument();
    expect(screen.getByDisplayValue('重载铁路')).toHaveAttribute('readonly');
  });
});
