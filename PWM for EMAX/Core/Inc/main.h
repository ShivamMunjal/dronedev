#ifndef __MAIN_H
#define __MAIN_H

#ifdef __cplusplus
extern "C" {
#endif

#include "stm32c0xx_ll_rcc.h"
#include "stm32c0xx_ll_bus.h"
#include "stm32c0xx_ll_system.h"
#include "stm32c0xx_ll_exti.h"
#include "stm32c0xx_ll_cortex.h"
#include "stm32c0xx_ll_utils.h"
#include "stm32c0xx_ll_pwr.h"
#include "stm32c0xx_ll_dma.h"
#include "stm32c0xx_ll_usart.h"
#include "stm32c0xx_ll_gpio.h"
#include "stm32c0xx_ll_tim.h"

/* NUCLEO-C092RC board defines */
#define LED1_Pin            LL_GPIO_PIN_5
#define LED1_GPIO_Port      GPIOA
#define LED2_Pin            LL_GPIO_PIN_9
#define LED2_GPIO_Port      GPIOC
#define USER_BUTTON_Pin     LL_GPIO_PIN_13
#define USER_BUTTON_GPIO_Port GPIOC

void Error_Handler(void);

#ifdef __cplusplus
}
#endif
#endif /* __MAIN_H */
