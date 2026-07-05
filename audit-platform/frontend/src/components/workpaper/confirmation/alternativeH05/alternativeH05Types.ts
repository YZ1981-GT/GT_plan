import type { AlternativeCompany } from '../alternativeD05/alternativeD05Types'

export interface AlternativeH05Payload {
  _format: 'alternative-h05-v1'
  companies: AlternativeCompany[]
}
