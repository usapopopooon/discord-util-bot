import { describe, it, expect, vi, beforeEach } from 'vitest'
import { clientFetch } from '../client-api'

describe('clientFetch', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('constructs the correct URL with /api/v1 prefix', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ result: 'ok' }),
    })
    global.fetch = mockFetch

    await clientFetch('/test')

    expect(mockFetch).toHaveBeenCalledWith(
      '/api/v1/test',
      expect.objectContaining({
        headers: expect.objectContaining({
          'Content-Type': 'application/json',
        }),
      })
    )
  })

  it('passes Content-Type header by default', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({}),
    })
    global.fetch = mockFetch

    await clientFetch('/test')

    const calledOptions = mockFetch.mock.calls[0][1]
    expect(calledOptions.headers['Content-Type']).toBe('application/json')
  })

  it('returns data on success', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ id: 1, name: 'test' }),
    })

    const result = await clientFetch<{ id: number; name: string }>('/test')

    expect(result.data).toEqual({ id: 1, name: 'test' })
    expect(result.error).toBeNull()
  })

  it('returns error message from JSON detail on failure', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      text: () => Promise.resolve(JSON.stringify({ detail: 'Not found' })),
    })

    const result = await clientFetch('/test')

    expect(result.data).toBeNull()
    expect(result.error).toBe('Not found')
  })

  it('returns error message from JSON message field', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      text: () => Promise.resolve(JSON.stringify({ message: 'Server error' })),
    })

    const result = await clientFetch('/test')

    expect(result.data).toBeNull()
    expect(result.error).toBe('Server error')
  })

  it('returns raw text when error response is not JSON', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      text: () => Promise.resolve('Internal Server Error'),
    })

    const result = await clientFetch('/test')

    expect(result.data).toBeNull()
    expect(result.error).toBe('Internal Server Error')
  })

  it('returns error message on network failure', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('Network error'))

    const result = await clientFetch('/test')

    expect(result.data).toBeNull()
    expect(result.error).toBe('Network error')
  })

  it("returns 'Unknown error' for non-Error throws", async () => {
    global.fetch = vi.fn().mockRejectedValue('some string')

    const result = await clientFetch('/test')

    expect(result.data).toBeNull()
    expect(result.error).toBe('Unknown error')
  })

  it('forwards custom options (method, body)', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({}),
    })
    global.fetch = mockFetch

    await clientFetch('/test', {
      method: 'POST',
      body: JSON.stringify({ key: 'value' }),
    })

    const calledOptions = mockFetch.mock.calls[0][1]
    expect(calledOptions.method).toBe('POST')
    expect(calledOptions.body).toBe(JSON.stringify({ key: 'value' }))
  })
})
