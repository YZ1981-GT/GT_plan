/**
 * Re-export apiProxy from services layer.
 * Some components import from this path for backward compatibility.
 */
import api from '@/services/apiProxy'

export const apiProxy = api
export default api
