// Dashboard - API Client
// API 호출 공통 함수

const API_BASE_URL = window.location.origin;

class TMSApi {
    constructor(baseUrl = API_BASE_URL) {
        this.baseUrl = baseUrl;
    }

    /**
     * Build query string from filters
     */
    buildQueryString(filters = {}) {
        const params = new URLSearchParams();
        
        Object.keys(filters).forEach(key => {
            if (filters[key]) {
                params.append(key, filters[key]);
            }
        });
        
        return params.toString();
    }

    /**
     * Generic GET request
     */
    async get(endpoint, filters = {}) {
        const queryString = this.buildQueryString(filters);
        const url = `${this.baseUrl}${endpoint}${queryString ? '?' + queryString : ''}`;
        
        try {
            const response = await fetch(url);
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.error || 'API request failed');
            }
            
            return data;
        } catch (error) {
            console.error(`API Error (${endpoint}):`, error);
            throw error;
        }
    }

    // ========================================================================
    // Dashboard APIs
    // ========================================================================
    async getDashboardKPI(filters) {
        return this.get('/api/dashboard/kpi', filters);
    }

    // ========================================================================
    // Shipment APIs
    // ========================================================================
    async getShipmentDailyTrend(filters) {
        return this.get('/api/shipment/daily-trend', filters);
    }

    async getShipmentByZone(filters) {
        return this.get('/api/shipment/by-zone', filters);
    }

    async getShipmentByDC(filters) {
        return this.get('/api/shipment/by-dc', filters);
    }

    // ========================================================================
    // Load APIs
    // ========================================================================
    async getLoadSummary(filters) {
        return this.get('/api/load/summary', filters);
    }

    async getLoadByCarrier(filters) {
        return this.get('/api/load/by-carrier', filters);
    }

    async getShipmentLoadMapping(filters) {
        return this.get('/api/load/shipment-mapping', filters);
    }

    // ========================================================================
    // Cost APIs
    // ========================================================================
    async getFreightCostAnalysis(filters) {
        return this.get('/api/cost/freight-analysis', filters);
    }

    async getSpotRateTrend(filters) {
        return this.get('/api/cost/spot-rate-trend', filters);
    }

    // ========================================================================
    // Network APIs
    // ========================================================================
    async getZoneNetworkAnalysis(filters) {
        return this.get('/api/network/zone-analysis', filters);
    }

    // ========================================================================
    // Model APIs
    // ========================================================================
    async getModelTopAnalysis(filters) {
        return this.get('/api/model/top-analysis', filters);
    }

    async getModelDailyTrend(filters) {
        return this.get('/api/model/daily-trend', filters);
    }

    // ========================================================================
    // Warehouse APIs
    // ========================================================================
    async getWarehousePerformance(filters) {
        return this.get('/api/warehouse/performance', filters);
    }

    async getWarehouseLeadtime(filters) {
        return this.get('/api/warehouse/leadtime', filters);
    }

    // ========================================================================
    // Utility APIs
    // ========================================================================
    async testConnection() {
        return this.get('/api/test-connection');
    }

    async healthCheck() {
        return this.get('/api/health');
    }
}

// Create global API instance
const tmsApi = new TMSApi();

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { TMSApi, tmsApi };
}
