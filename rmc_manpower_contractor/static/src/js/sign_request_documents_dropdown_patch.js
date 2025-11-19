/** @odoo-module **/

import { patch } from '@web/core/utils/patch';
import { SignRequestDocumentsDropdown } from '@sign/backend_components/sign_request/sign_request_documents_dropdown';

patch(SignRequestDocumentsDropdown.prototype, {
    patchName: 'rmc_manpower_contractor.SignRequestDocumentsDropdown',
    async fetchSignRequestData() {
        const signRequestId = this.props.record?.context?.active_id;
        if (!signRequestId) {
            this.signInfo.set({
                documentId: false,
                signRequestToken: false,
                signRequestState: false,
            });
            return;
        }

        const signRequestData = await this.orm.read(
            'sign.request',
            [signRequestId],
            ['access_token', 'state']
        );

        if (signRequestData && signRequestData.length) {
            const [{ access_token: token = false, state = false }] = signRequestData;
            this.signInfo.set({
                documentId: signRequestId,
                signRequestToken: token,
                signRequestState: state,
            });
        } else {
            this.signInfo.set({
                documentId: signRequestId,
                signRequestToken: false,
                signRequestState: false,
            });
        }
    },
});
