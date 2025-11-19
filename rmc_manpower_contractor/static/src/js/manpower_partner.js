/** @odoo-module **/

document.addEventListener('DOMContentLoaded', () => {
    const root = document.querySelector('.o_manpower_partner');
    if (!root) {
        return;
    }

    const faqItems = root.querySelectorAll('.faq-item');
    faqItems.forEach((item) => {
        const question = item.querySelector('.faq-question');
        question?.addEventListener('click', () => {
            const isActive = item.classList.contains('active');
            faqItems.forEach((faq) => faq.classList.remove('active'));
            if (!isActive) {
                item.classList.add('active');
            }
        });
    });

    const navLinks = root.querySelectorAll('a[href^="#"]');
    navLinks.forEach((link) => {
        link.addEventListener('click', (ev) => {
            const href = link.getAttribute('href');
            if (!href || href === '#') {
                return;
            }
            const target = root.querySelector(href);
            if (!target) {
                return;
            }
            ev.preventDefault();
            const headerOffset = 90;
            const elementTop = target.getBoundingClientRect().top + window.pageYOffset;
            window.scrollTo({ top: elementTop - headerOffset, behavior: 'smooth' });
        });
    });

    const contractorForm = root.querySelector('#contractorForm');
    const successMessage = root.querySelector('#successMessage');

    if (contractorForm) {
        contractorForm.addEventListener('submit', (ev) => {
            ev.preventDefault();
            const formData = new FormData(contractorForm);
            const contractTypes = formData.getAll('contractType');
            if (!contractTypes.length) {
                window.alert('Please select at least one contract type.');
                return;
            }
            const docsInput = contractorForm.querySelector('#documents');
            if (docsInput && !docsInput.files.length) {
                window.alert('Please upload required documents.');
                return;
            }

            const submitButton = contractorForm.querySelector('.btn-submit');
            const originalText = submitButton?.innerHTML;
            if (submitButton) {
                submitButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Submitting...';
                submitButton.disabled = true;
            }

            window.setTimeout(() => {
                contractorForm.style.display = 'none';
                if (successMessage) {
                    successMessage.style.display = 'block';
                    successMessage.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
                if (submitButton && originalText) {
                    submitButton.innerHTML = originalText;
                    submitButton.disabled = false;
                }
            }, 1500);
        });
    }

    const stickyButton = root.querySelector('.sticky-apply-btn');
    const applySection = root.querySelector('#apply');
    window.addEventListener('scroll', () => {
        if (!stickyButton || !applySection) {
            return;
        }
        const sectionTop = applySection.offsetTop;
        const sectionBottom = sectionTop + applySection.offsetHeight;
        const scrollBottom = window.pageYOffset + window.innerHeight;
        if (scrollBottom > sectionTop && window.pageYOffset < sectionBottom - 200) {
            stickyButton.style.opacity = '0';
            stickyButton.style.pointerEvents = 'none';
        } else {
            stickyButton.style.opacity = '1';
            stickyButton.style.pointerEvents = 'auto';
        }
    });

    const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
            if (entry.isIntersecting) {
                entry.target.style.opacity = '1';
                entry.target.style.transform = 'translateY(0)';
            }
        });
    }, { threshold: 0.1, rootMargin: '0px 0px -50px 0px' });

    const animated = root.querySelectorAll('.benefit-card, .contract-card, .requirement-item, .step, .faq-item');
    animated.forEach((element) => {
        element.style.opacity = '0';
        element.style.transform = 'translateY(20px)';
        element.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
        observer.observe(element);
    });

    const phoneInput = root.querySelector('#phone');
    phoneInput?.addEventListener('input', (ev) => {
        let value = ev.target.value.replace(/\D/g, '');
        if (value.length > 10) {
            value = value.slice(0, 10);
        }
        ev.target.value = value;
    });

    const documentsInput = root.querySelector('#documents');
    documentsInput?.addEventListener('change', (ev) => {
        const files = ev.target.files;
        if (!files.length) {
            return;
        }
        const names = Array.from(files).slice(0, 3).map((file) => file.name);
        let message = names.join(', ');
        if (files.length > 3) {
            message += ` and ${files.length - 3} more file(s)`;
        }
        let info = root.querySelector('.file-list-display');
        if (!info) {
            info = document.createElement('div');
            info.className = 'file-list-display';
            documentsInput.parentNode.appendChild(info);
        }
        info.innerHTML = `<i class="fas fa-check-circle" style="color: #10b981; margin-right: 0.5rem;"></i>${files.length} file(s) selected: ${message}`;
    });
});
